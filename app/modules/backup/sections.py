"""Разделы резервной копии портала: по одному на модуль с данными.

Каждый раздел умеет две вещи: выгрузить свои данные в обычные словари и
списки (даты — строками ISO, без объектов SQLAlchemy) и восстановить их
обратно через ORM, сохраняя идентификаторы: на них ссылаются внешние ключи
(``template_blocks.section_id`` и ``created_by``, ``tasks.assignee_id`` и
``created_by``, связи ``block_tags``).

Порядок регистрации задан зависимостями (см. ``registry.py``):

1. ``users`` — сотрудники, на них ссылаются заготовки и карточки;
2. ``inheritance`` — справочник региональных тарифов;
3. ``templates_db`` — разделы, теги, заготовки и связи «заготовка — тег»;
4. ``tasks`` — карточки доски, включая корзину (``deleted_at``);
5. ``google_calendar`` — файлы ключа и токена: пишутся после фиксации БД.

Пароли пользователей в копию попадают только по флагу «Включить открытые
пароли»: без него в файле нет ни ``hashed_password``, ни ``password_plain``.
Хеш нельзя восстановить из открытого пароля, поэтому при включённом флаге
пишутся оба поля: хеш — рабочий вход сотрудника, ``password_plain`` — для
выдачи пароля нотариусом. Подробности — в docstring ``_import_users``.
"""
import secrets
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.security import hash_password
from app.modules.auth.models import DEFAULT_MARKER_COLOR, User
from app.modules.auth.schemas import name_key
from app.modules.backup import registry
from app.modules.backup.registry import BackupSection, BackupValidationError
from app.modules.google_calendar import service as google_calendar
from app.modules.settings.models import InheritanceTariff
from app.modules.tasks.models import Task
from app.modules.templates_db.models import Section, Tag, TemplateBlock, block_tags

# Подписи разделов: попадают в сообщения нотариусу и в отчёт
TITLE_USERS = "Пользователи"
TITLE_INHERITANCE = "Региональные тарифы"
TITLE_TEMPLATES_DB = "База данных (разделы, теги, заготовки)"
TITLE_TASKS = "Задачи"
TITLE_GOOGLE_CALENDAR = "Google Календарь"


# ── Общие помощники: выгрузка значений в JSON ──────────────────────────────


def _iso(value: date | datetime | None) -> str | None:
    """Дата и время в файле — строка ISO (как они лежат в БД, без пояса)."""
    return value.isoformat() if value is not None else None


def _utc_now() -> datetime:
    """Текущее время UTC без пояса: в том же виде, что в БД."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _random_password() -> str:
    """Случайный пароль для сотрудника, которому копия пароль не несёт."""
    return secrets.token_urlsafe(32)


# ── Общие помощники: проверка строк при восстановлении ─────────────────────


def _field_error(title: str, index: int, field_name: str) -> BackupValidationError:
    """Ошибка значения поля в строке раздела — с номером строки для нотариуса."""
    return BackupValidationError(
        f"{title}: строка № {index}, поле «{field_name}» — неверное значение"
    )


def _require_rows(payload: dict[str, Any], title: str) -> list[dict[str, Any]]:
    """Список строк раздела: поле ``rows``, каждый элемент — объект."""
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise BackupValidationError(f"{title}: в копии нет списка строк «rows»")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise BackupValidationError(f"{title}: строка № {index} — не объект JSON")
    return rows


def _field_rows(
    payload: dict[str, Any], field_name: str, title: str
) -> list[dict[str, Any]]:
    """Список объектов в именованном поле составного раздела."""
    rows = payload.get(field_name)
    if not isinstance(rows, list):
        raise BackupValidationError(f"{title}: в копии нет списка «{field_name}»")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise BackupValidationError(
                f"{title}: «{field_name}», строка № {index} — не объект JSON"
            )
    return rows


def _require_int(row: dict[str, Any], field_name: str, title: str, index: int) -> int:
    """Обязательное целое поле: ``True``/``False`` числом не считается."""
    value = row.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _field_error(title, index, field_name)
    return value


def _optional_int(
    row: dict[str, Any], field_name: str, title: str, index: int
) -> int | None:
    """Необязательное целое поле: отсутствие и ``null`` — это ``None``."""
    value = row.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _field_error(title, index, field_name)
    return value


def _optional_str(
    row: dict[str, Any], field_name: str, title: str, index: int
) -> str | None:
    """Необязательное строковое поле."""
    value = row.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _field_error(title, index, field_name)
    return value


def _require_str(row: dict[str, Any], field_name: str, title: str, index: int) -> str:
    """Обязательное непустое строковое поле."""
    value = _optional_str(row, field_name, title, index)
    if value is None or not value.strip():
        raise _field_error(title, index, field_name)
    return value


def _optional_bool(
    row: dict[str, Any], field_name: str, title: str, index: int
) -> bool | None:
    """Необязательное логическое поле."""
    value = row.get(field_name)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise _field_error(title, index, field_name)
    return value


def _optional_datetime(
    row: dict[str, Any], field_name: str, title: str, index: int
) -> datetime | None:
    """Необязательное поле даты-времени: строка ISO."""
    value = row.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _field_error(title, index, field_name)
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise _field_error(title, index, field_name) from exc


def _optional_date(
    row: dict[str, Any], field_name: str, title: str, index: int
) -> date | None:
    """Необязательное поле даты: строка ISO (``2026-10-31``)."""
    value = row.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _field_error(title, index, field_name)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _field_error(title, index, field_name) from exc



# ── Сотрудники ─────────────────────────────────────────────────────────────


async def _export_users(db: AsyncSession) -> dict[str, Any]:
    """Сотрудники портала: все колонки, кроме паролей (те — по флагу).

    ``hashed_password`` и ``password_plain`` пишутся только по флагу
    «Включить открытые пароли»: такой файл нужно хранить как секрет.
    """
    include_passwords = bool(registry.options().get("include_plain_passwords"))
    result = await db.execute(select(User).order_by(User.id))
    rows: list[dict[str, Any]] = []
    for user in result.scalars().all():
        row: dict[str, Any] = {
            "id": user.id,
            "full_name": user.full_name,
            "name_key": user.name_key,
            "marker_color": user.marker_color,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": _iso(user.created_at),
        }
        if include_passwords:
            row["hashed_password"] = user.hashed_password
            row["password_plain"] = user.password_plain
        rows.append(row)
    return {"rows": rows}


async def _import_users(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Возвращает сотрудников к состоянию копии, сохраняя идентификаторы.

    Копия без паролей (флаг «Включить открытые пароли» не стоял) паролей не
    содержит, поэтому:

    * у сотрудника, который уже есть в портале с тем же ``id``, остаётся его
      прежний пароль (хеш и открытый пароль не меняются);
    * новый сотрудник импортируется **неактивным** (``is_active`` = False)
      со случайным паролем, которого не знает никто: войти он не сможет,
      пока нотариус не выдаст пароль в разделе «Пользователи». Об этом
      пишется предупреждение в отчёт о восстановлении.

    Копия с паролями восстанавливает и хеш, и открытый пароль как есть.
    Таблиц у раздела нет в ``clear``: прежние пароли читаются здесь же,
    до очистки таблицы ``users``, — иначе сохранять было бы нечего.
    """
    title = TITLE_USERS
    rows = _require_rows(payload, title)

    # Прежние пароли читаем до очистки: копия без паролей их не заменяет
    existing = {
        user.id: (user.hashed_password, user.password_plain)
        for user in (await db.execute(select(User))).scalars().all()
    }
    await db.execute(delete(User))
    await db.flush()

    seen_keys: set[str] = set()
    without_password: list[str] = []
    for index, row in enumerate(rows, start=1):
        user_id = _require_int(row, "id", title, index)
        full_name = _require_str(row, "full_name", title, index)
        row_key = _optional_str(row, "name_key", title, index) or name_key(full_name)
        if row_key in seen_keys:
            raise BackupValidationError(
                f"{title}: строка № {index} — сотрудник «{full_name}» есть в копии дважды"
            )
        seen_keys.add(row_key)

        hashed_password = _optional_str(row, "hashed_password", title, index)
        password_plain = _optional_str(row, "password_plain", title, index)
        is_active = _optional_bool(row, "is_active", title, index)
        if hashed_password is None:
            kept = existing.get(user_id)
            if kept is not None:
                # Сотрудник уже был в портале: его пароль остаётся рабочим
                hashed_password, kept_plain = kept
                password_plain = kept_plain
            else:
                # Новому сотруднику пароль не назначается: вход закрыт
                hashed_password = hash_password(_random_password())
                password_plain = None
                without_password.append(full_name)
                is_active = False

        db.add(
            User(
                id=user_id,
                full_name=full_name,
                name_key=row_key,
                hashed_password=hashed_password,
                password_plain=password_plain,
                marker_color=(
                    _optional_str(row, "marker_color", title, index)
                    or DEFAULT_MARKER_COLOR
                ),
                role=_optional_str(row, "role", title, index) or "user",
                is_active=True if is_active is None else is_active,
                created_at=_optional_datetime(row, "created_at", title, index)
                or _utc_now(),
            )
        )

    if without_password:
        registry.warn(
            "Сотрудники без пароля в копии импортированы неактивными: "
            + ", ".join(without_password)
            + ". Выдайте им пароль в разделе «Пользователи»."
        )


# ── Региональные тарифы для наследства ─────────────────────────────────────


async def _export_inheritance(db: AsyncSession) -> dict[str, Any]:
    """Справочник «вид имущества — региональный тариф»."""
    result = await db.execute(select(InheritanceTariff).order_by(InheritanceTariff.id))
    rows = [
        {"id": item.id, "asset_type": item.asset_type, "rate": item.rate}
        for item in result.scalars().all()
    ]
    return {"rows": rows}


async def _clear_inheritance(db: AsyncSession) -> None:
    """Удаляет все строки справочника перед восстановлением."""
    await db.execute(delete(InheritanceTariff))


async def _import_inheritance(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Возвращает справочник к состоянию копии, сохраняя идентификаторы."""
    title = TITLE_INHERITANCE
    for index, row in enumerate(_require_rows(payload, title), start=1):
        db.add(
            InheritanceTariff(
                id=_require_int(row, "id", title, index),
                asset_type=_require_str(row, "asset_type", title, index),
                rate=_require_int(row, "rate", title, index),
            )
        )


# ── База заготовок: разделы, теги, заготовки, связи ────────────────────────


async def _export_templates_db(db: AsyncSession) -> dict[str, Any]:
    """Заготовки со своими разделами, тегами и связями «заготовка — тег»."""
    sections = [
        {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "sort_order": item.sort_order,
            "created_at": _iso(item.created_at),
        }
        for item in (await db.execute(select(Section).order_by(Section.id)))
        .scalars()
        .all()
    ]
    tags = [
        {"id": item.id, "name": item.name}
        for item in (await db.execute(select(Tag).order_by(Tag.id))).scalars().all()
    ]
    blocks = [
        {
            "id": item.id,
            "section_id": item.section_id,
            "title": item.title,
            "body": item.body,
            "created_by": item.created_by,
            "created_at": _iso(item.created_at),
            "updated_at": _iso(item.updated_at),
        }
        for item in (await db.execute(select(TemplateBlock).order_by(TemplateBlock.id)))
        .scalars()
        .all()
    ]
    links = await db.execute(
        select(block_tags.c.block_id, block_tags.c.tag_id).order_by(
            block_tags.c.block_id, block_tags.c.tag_id
        )
    )
    return {
        "sections": sections,
        "tags": tags,
        "blocks": blocks,
        "block_tags": [
            {"block_id": row.block_id, "tag_id": row.tag_id} for row in links.all()
        ],
    }


async def _clear_templates_db(db: AsyncSession) -> None:
    """Удаляет заготовки в порядке, обратном зависимостям."""
    await db.execute(delete(block_tags))
    await db.execute(delete(TemplateBlock))
    await db.execute(delete(Tag))
    await db.execute(delete(Section))


async def _import_templates_db(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Восстанавливает разделы, теги, заготовки и связи, сохраняя id.

    Порядок вставки внутри раздела задан внешними ключами: разделы и теги —
    до заготовок, связи «заготовка — тег» — последними.
    """
    title = TITLE_TEMPLATES_DB
    section_rows = _field_rows(payload, "sections", title)
    tag_rows = _field_rows(payload, "tags", title)
    block_rows = _field_rows(payload, "blocks", title)
    link_rows = _field_rows(payload, "block_tags", title)

    for index, row in enumerate(section_rows, start=1):
        db.add(
            Section(
                id=_require_int(row, "id", title, index),
                name=_require_str(row, "name", title, index),
                description=_optional_str(row, "description", title, index),
                sort_order=_optional_int(row, "sort_order", title, index) or 0,
                created_at=_optional_datetime(row, "created_at", title, index)
                or _utc_now(),
            )
        )
    for index, row in enumerate(tag_rows, start=1):
        db.add(
            Tag(
                id=_require_int(row, "id", title, index),
                name=_require_str(row, "name", title, index),
            )
        )
    await db.flush()

    for index, row in enumerate(block_rows, start=1):
        db.add(
            TemplateBlock(
                id=_require_int(row, "id", title, index),
                section_id=_require_int(row, "section_id", title, index),
                title=_require_str(row, "title", title, index),
                body=_optional_str(row, "body", title, index) or "",
                created_by=_optional_int(row, "created_by", title, index),
                created_at=_optional_datetime(row, "created_at", title, index)
                or _utc_now(),
                updated_at=_optional_datetime(row, "updated_at", title, index)
                or _utc_now(),
            )
        )
    await db.flush()

    if link_rows:
        await db.execute(
            insert(block_tags),
            [
                {
                    "block_id": _require_int(row, "block_id", title, index),
                    "tag_id": _require_int(row, "tag_id", title, index),
                }
                for index, row in enumerate(link_rows, start=1)
            ],
        )


# ── Карточки доски «Задачи» ────────────────────────────────────────────────


async def _export_tasks(db: AsyncSession) -> dict[str, Any]:
    """Карточки доски вместе с корзиной (``deleted_at``) и местом в столбце."""
    result = await db.execute(select(Task).order_by(Task.id))
    rows = [
        {
            "id": task.id,
            "title": task.title,
            "contact": task.contact,
            "due_date": _iso(task.due_date),
            "description": task.description,
            "assignee_id": task.assignee_id,
            "card_type": task.card_type,
            "status": task.status,
            "checklist": dict(task.checklist or {}),
            "created_by": task.created_by,
            "created_at": _iso(task.created_at),
            "updated_at": _iso(task.updated_at),
            "deleted_at": _iso(task.deleted_at),
            "position": task.position,
        }
        for task in result.scalars().all()
    ]
    return {"rows": rows}


async def _clear_tasks(db: AsyncSession) -> None:
    """Удаляет все карточки — и с доски, и из корзины."""
    await db.execute(delete(Task))


def _checklist(row: dict[str, Any], title: str, index: int) -> dict[str, bool]:
    """Чек-лист карточки: объект «пункт: отметка» без посторонних значений."""
    value = row.get("checklist")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise _field_error(title, index, "checklist")
    checklist: dict[str, bool] = {}
    for item, checked in value.items():
        if not isinstance(item, str) or not isinstance(checked, bool):
            raise _field_error(title, index, "checklist")
        checklist[item] = checked
    return checklist


async def _import_tasks(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Восстанавливает карточки доски, сохраняя id, порядок и корзину."""
    title = TITLE_TASKS
    for index, row in enumerate(_require_rows(payload, title), start=1):
        db.add(
            Task(
                id=_require_int(row, "id", title, index),
                title=_require_str(row, "title", title, index),
                contact=_optional_str(row, "contact", title, index),
                due_date=_optional_date(row, "due_date", title, index),
                description=_optional_str(row, "description", title, index),
                assignee_id=_optional_int(row, "assignee_id", title, index),
                card_type=_optional_str(row, "card_type", title, index) or "other",
                status=_optional_str(row, "status", title, index) or "queue",
                checklist=_checklist(row, title, index),
                created_by=_optional_int(row, "created_by", title, index),
                created_at=_optional_datetime(row, "created_at", title, index)
                or _utc_now(),
                updated_at=_optional_datetime(row, "updated_at", title, index)
                or _utc_now(),
                deleted_at=_optional_datetime(row, "deleted_at", title, index),
                position=_optional_int(row, "position", title, index) or 0,
            )
        )


# ── Google Календарь: файлы ключа, токена и почты ─────────────────────────


async def _export_google_calendar(db: AsyncSession) -> dict[str, Any]:
    """Состояние связи с календарём; содержимое файлов — по флагу «секреты»."""
    include_credentials = bool(registry.options().get("include_google_credentials"))
    return await run_in_threadpool(
        google_calendar.export_state, include_credentials=include_credentials
    )


async def _import_google_calendar(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Возвращает ключ, токен и почту аккаунта на место (после commit БД).

    Файлы, которых в копии нет, не удаляются: восстановление старой копии
    без секретов не должно молча разрывать уже настроенную связь. О таком
    пропуске раздел сообщает предупреждением в отчёт.
    """
    include_credentials = bool(payload.get("credentials") or payload.get("token"))
    try:
        await run_in_threadpool(
            google_calendar.import_state, payload, include_credentials
        )
    except google_calendar.GoogleCalendarError as exc:
        raise BackupValidationError(str(exc)) from exc
    if not include_credentials:
        registry.warn(
            "В копии нет ключа и токена Google Календаря — файлы на компьютере "
            "портала оставлены как были."
        )


# ── Регистрация разделов ───────────────────────────────────────────────────

# Порядок в кортеже — порядок зависимостей: users первым, файлы Google последними
SECTIONS: tuple[BackupSection, ...] = (
    BackupSection(
        key="users",
        title=TITLE_USERS,
        order=10,
        export=_export_users,
        import_=_import_users,
    ),
    BackupSection(
        key="inheritance",
        title=TITLE_INHERITANCE,
        order=20,
        export=_export_inheritance,
        import_=_import_inheritance,
        clear=_clear_inheritance,
    ),
    BackupSection(
        key="templates_db",
        title=TITLE_TEMPLATES_DB,
        order=30,
        export=_export_templates_db,
        import_=_import_templates_db,
        clear=_clear_templates_db,
    ),
    BackupSection(
        key="tasks",
        title=TITLE_TASKS,
        order=40,
        export=_export_tasks,
        import_=_import_tasks,
        clear=_clear_tasks,
    ),
    BackupSection(
        key="google_calendar",
        title=TITLE_GOOGLE_CALENDAR,
        order=50,
        export=_export_google_calendar,
        import_=_import_google_calendar,
        after_commit=True,
    ),
)


def register_sections() -> None:
    """Добавляет разделы портала в реестр резервных копий."""
    for section in SECTIONS:
        registry.register(section)
