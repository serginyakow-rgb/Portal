"""Бизнес-логика модуля «Задачи»: доска, карточки, перемещение и корзина.

Модуль не импортирует модели других модулей: имя исполнителя берётся из
связи assignee (она загружается вместе с карточкой), а список сотрудников
для фильтра роуты получают из auth.service.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.models import Task
from app.modules.tasks.schemas import (
    CARD_TYPE_LABELS,
    DEFAULT_STATUS,
    STATUS_ORDER,
    TaskCreate,
    TaskListItem,
    TaskRead,
    TaskStatus,
    TaskUpdate,
)


def _now() -> datetime:
    """Текущее время UTC без пояса — в том же виде, что CURRENT_TIMESTAMP в БД."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Сколько рабочих дней (пн–пт) может остаться до срока, чтобы он считался
# срочным: меньше этого числа — срок выделяется красным в карточке доски
DUE_SOON_WORKDAYS = 2

# Рабочая неделя: понедельник (0) — пятница (4); суббота и воскресенье — выходные
WORKWEEK_DAYS = 5

# Столбцы, которые считаются текущей работой сотрудника: «На очереди» и «В работе».
# По ним считается второе число метки «Задачи» в левом меню (count_menu_badge)
MENU_BADGE_STATUSES: tuple[str, ...] = (DEFAULT_STATUS, "in_progress")

# Прогресс карточки в процентах (0–100) для полосы под строкой «Исполнитель | Срок».
# Без исполнителя — 0; с исполнителем и без чек-листа: «На очереди» — 10,
# «В работе» — 50, «Проверка»/«Готово» — 100. Карточка с чек-листом в «На очереди»
# тоже 10, в «В работе» начинается с 10, в закрытых столбцах — с 20, а 80% делятся
# поровну между пунктами чек-листа: в «Готово» со всеми пунктами получается 100.
PROGRESS_NONE = 0
PROGRESS_QUEUE = 10
PROGRESS_IN_PROGRESS = 50
PROGRESS_CLOSED = 100
# Карточка с чек-листом: база «В работе» — 10, «Проверка»/«Готово» — 20,
# остальные 80% приносят отмеченные пункты
PROGRESS_CHECKLIST_IN_PROGRESS = 10
PROGRESS_CHECKLIST_CLOSED = 20
PROGRESS_CHECKLIST_SHARE = 80
# Столбцы, где работа считается закрытой: «Проверка» и «Готово»
PROGRESS_CLOSED_STATUSES: tuple[str, ...] = ("review", "done")


def _checklist_share(items: dict[str, bool]) -> int:
    """Доля отмеченных пунктов: 80/число пунктов чек-листа за каждый отмеченный."""
    checked = sum(1 for flag in items.values() if flag)
    return round(PROGRESS_CHECKLIST_SHARE * checked / len(items))


def task_progress(
    status: str,
    assignee_id: int | None,
    checklist: dict[str, bool] | None = None,
) -> int:
    """Прогресс карточки для полосы в карточке доски: проценты 0–100.

    Карточка без исполнителя — 0, даже если пункты отмечены: работу никто
    не взял. С исполнителем в «На очереди» — 10, чек-лист не учитывается
    (работа ещё не начата). Без чек-листа «В работе» — 50, «Проверка» и
    «Готово» — 100: столбец сам говорит, где карточка. С чек-листом «В работе»
    даёт 10 и прибавляет 80/число пунктов за каждый отмеченный, «Проверка»
    и «Готово» — 20 и те же 80%: видно, все ли пункты закрыты (100 — все).

    Чек-лист карточки хранит все пункты её типа (schemas.keep_type_checklist),
    поэтому число чекбоксов — это len(checklist); у типов без чек-листа
    (inheritance, other) словарь пустой, и работает правило без чекбоксов.
    """
    if assignee_id is None:
        return PROGRESS_NONE
    items = dict(checklist or {})
    if status == DEFAULT_STATUS:
        # «На очереди»: работа ещё не начата, отметки прогресс не двигают
        return PROGRESS_QUEUE
    if status in PROGRESS_CLOSED_STATUSES:
        if not items:
            return PROGRESS_CLOSED
        return PROGRESS_CHECKLIST_CLOSED + _checklist_share(items)
    if not items:
        return PROGRESS_IN_PROGRESS
    return PROGRESS_CHECKLIST_IN_PROGRESS + _checklist_share(items)


def working_days_left(due_date: date | None, today: date | None = None) -> int | None:
    """Сколько рабочих дней осталось до срока, не считая сегодняшний день.

    Рабочие дни — понедельник–пятница, суббота и воскресенье пропускаются.
    Срок сегодня или в прошлом даёт 0 (карточка считается срочной), пустой
    срок — None. Считаем по календарным неделям: в каждой полной неделе ровно
    пять рабочих дней, остаток (до шести дней) перебираем по одному — иначе
    срок в следующем году прокручивал бы сотни шагов на каждую карточку.
    """
    if due_date is None:
        return None
    start = today or date.today()
    if due_date <= start:
        return 0
    days = (due_date - start).days
    full_weeks, rest = divmod(days, 7)
    remaining = full_weeks * WORKWEEK_DAYS
    for offset in range(1, rest + 1):
        if (start + timedelta(days=offset)).weekday() < WORKWEEK_DAYS:
            remaining += 1
    return remaining


def _due_sort_key(task: Task) -> tuple[bool, date]:
    """Ключ сортировки карточки по сроку: без срока — в конце столбца."""
    return (task.due_date is None, task.due_date or date.min)


def _to_list_item(task: Task) -> TaskListItem:
    """Карточка доски: подпись типа и имя исполнителя берутся из справочника и связи.

    Описание и чек-лист попадают в элемент списка для окна правки: на доске
    они не выводятся, но шаблон отдаёт их в data-task на карточке.
    Прогресс для полосы в карточке считает task_progress: он зависит от
    столбца, исполнителя и отмеченных пунктов чек-листа.
    """
    days_left = working_days_left(task.due_date)
    return TaskListItem(
        id=task.id,
        title=task.title,
        contact=task.contact,
        due_date=task.due_date,
        description=task.description,
        card_type=task.card_type,
        card_type_label=CARD_TYPE_LABELS.get(task.card_type, task.card_type),
        status=task.status,
        position=task.position,
        assignee_id=task.assignee_id,
        assignee_name=task.assignee.full_name if task.assignee else None,
        assignee_color=task.assignee.marker_color if task.assignee else None,
        progress=task_progress(task.status, task.assignee_id, task.checklist),
        due_soon=days_left is not None and days_left < DUE_SOON_WORKDAYS,
        checklist=dict(task.checklist or {}),
        deleted_at=task.deleted_at,
    )


def _to_read(task: Task) -> TaskRead:
    """Полное представление карточки для страницы правки."""
    return TaskRead(
        id=task.id,
        title=task.title,
        contact=task.contact,
        due_date=task.due_date,
        description=task.description,
        assignee_id=task.assignee_id,
        assignee_name=task.assignee.full_name if task.assignee else None,
        card_type=task.card_type,
        status=task.status,
        checklist=dict(task.checklist or {}),
        created_by=task.created_by,
        created_at=task.created_at,
        updated_at=task.updated_at,
        deleted_at=task.deleted_at,
        position=task.position,
    )


def group_by_status(tasks: list[TaskListItem]) -> dict[str, list[TaskListItem]]:
    """Раскладывает карточки по столбцам в порядке STATUS_ORDER.

    Пустые столбцы остаются в словаре: доска всегда показывает четыре колонки.
    """
    columns: dict[str, list[TaskListItem]] = {status: [] for status in STATUS_ORDER}
    for task in tasks:
        columns.setdefault(task.status, []).append(task)
    return columns


async def _column_tasks(
    db: AsyncSession,
    status: str,
    *,
    exclude_id: int | None = None,
) -> list[Task]:
    """Карточки одного столбца по порядку; exclude_id убирает перемещаемую карточку."""
    stmt = select(Task).where(Task.deleted_at.is_(None), Task.status == status)
    if exclude_id is not None:
        stmt = stmt.where(Task.id != exclude_id)
    result = await db.execute(stmt.order_by(Task.position, Task.id))
    return list(result.scalars().all())


async def _next_position(db: AsyncSession, status: str) -> int:
    """Свободная позиция в конце столбца."""
    stmt = select(func.max(Task.position)).where(
        Task.deleted_at.is_(None),
        Task.status == status,
    )
    last = (await db.execute(stmt)).scalar()
    return 0 if last is None else last + 1


def _matches_query(task: Task, needle: str) -> bool:
    """Совпадение поисковой строки хотя бы с одним полем карточки.

    Ищем по заголовку, контакту и описанию без учёта регистра. Сравнение
    идёт в Python: SQLite приводит регистр только у латиницы, поэтому
    LIKE по запросу «дкп» не нашёл бы карточку «ДКП».
    """
    fields = (task.title, task.contact, task.description)
    return any(needle in (value or "").casefold() for value in fields)


async def list_board(
    db: AsyncSession,
    *,
    assignee_id: int | None = None,
    query: str = "",
) -> list[TaskListItem]:
    """Карточки доски в порядке показа: только неудалённые, по сроку.

    В каждом столбце срок идёт по возрастанию, карточки без срока («не задан»)
    стоят в конце; при одинаковых сроках сохраняется ручной порядок
    перетаскивания (position). Фильтры — исполнитель и поиск.

    Фильтр по исполнителю показывает карточки выбранного сотрудника вместе
    с карточками без исполнителя: «ничьи» карточки остаются видны в списке
    любого сотрудника, иначе после выбора фильтра они терялись бы с доски.
    """
    stmt = select(Task).where(Task.deleted_at.is_(None))
    if assignee_id is not None:
        # Карточки сотрудника и карточки без исполнителя (assignee_id IS NULL):
        # «ничьи» карточки видны в списке любого сотрудника
        stmt = stmt.where(
            or_(Task.assignee_id == assignee_id, Task.assignee_id.is_(None))
        )
    result = await db.execute(
        stmt.order_by(
            # IS NULL даёт 0 у карточек со сроком и 1 у пустых — пустые в конце
            Task.due_date.is_(None),
            Task.due_date,
            Task.position,
            Task.id,
        )
    )
    tasks = list(result.scalars().all())
    # Пустая строка (поле поиска не заполнено) ничего не отсеивает
    needle = query.strip().casefold()
    if needle:
        tasks = [task for task in tasks if _matches_query(task, needle)]
    return [_to_list_item(task) for task in tasks]


async def list_trash(db: AsyncSession) -> list[TaskListItem]:
    """Корзина: последние удалённые сверху."""
    result = await db.execute(
        select(Task)
        .where(Task.deleted_at.is_not(None))
        .order_by(Task.deleted_at.desc(), Task.id.desc())
    )
    return [_to_list_item(task) for task in result.scalars().all()]


async def count_trash(db: AsyncSession) -> int:
    """Сколько карточек в корзине: число для бейджа на странице."""
    stmt = select(func.count(Task.id)).where(Task.deleted_at.is_not(None))
    return (await db.execute(stmt)).scalar_one()


async def count_tasks_by_assignee(db: AsyncSession) -> dict[int, int]:
    """Сколько карточек закреплено за каждым сотрудником: {id: число}.

    Считаются все столбцы доски, но не корзина: закреплённой карточка
    остаётся, пока у неё есть исполнитель и она не удалена. Сотрудники
    без карточек в словарь не попадают — окно «Задачи по сотрудникам»
    показывает им ноль (assignee_counts.get в шаблоне).
    """
    stmt = (
        select(Task.assignee_id, func.count(Task.id))
        .where(Task.deleted_at.is_(None), Task.assignee_id.is_not(None))
        .group_by(Task.assignee_id)
    )
    rows = (await db.execute(stmt)).all()
    return {assignee_id: count for assignee_id, count in rows}


@dataclass(frozen=True)
class TasksMenuBadge:
    """Два числа метки «Задачи» в левом меню портала."""

    unassigned: int  # карточки без исполнителя
    mine: int  # карточки сотрудника в «На очереди» и «В работе»


async def count_menu_badge(db: AsyncSession, user_id: int) -> TasksMenuBadge:
    """Числа для метки «Задачи»: ничьи карточки и карточки сотрудника в работе.

    Первое число — неудалённые карточки без исполнителя (любой столбец доски).
    Второе — карточки этого сотрудника в столбцах «На очереди» и «В работе»
    (MENU_BADGE_STATUSES). Карточки без исполнителя в него не входят, хотя доска
    показывает их в списке любого сотрудника: метка отражает личную загрузку.

    Оба числа считаются одним запросом: count(case …) на SQLite подходит
    везде, в отличие от FILTER, доступного только с 3.30.
    """
    mine_condition = and_(
        Task.assignee_id == user_id,
        Task.status.in_(MENU_BADGE_STATUSES),
    )
    unassigned = func.count(case((Task.assignee_id.is_(None), Task.id)))
    mine = func.count(case((mine_condition, Task.id)))
    row = (
        await db.execute(select(unassigned, mine).where(Task.deleted_at.is_(None)))
    ).one()
    return TasksMenuBadge(unassigned=row[0], mine=row[1])


async def get_task(db: AsyncSession, task_id: int) -> Task | None:
    """Карточка по идентификатору — вместе с исполнителем и автором.

    Карточки корзины тоже находятся: восстановление и окончательное удаление
    проверяют deleted_at сами.
    """
    return await db.get(Task, task_id)


async def read_task(db: AsyncSession, task_id: int) -> TaskRead | None:
    """Представление карточки для формы правки."""
    task = await get_task(db, task_id)
    return _to_read(task) if task is not None else None


async def create_task(
    db: AsyncSession,
    data: TaskCreate,
    *,
    created_by: int | None = None,
) -> Task:
    """Создаёт карточку в конце столбца «На очереди».

    Тип карточки и чек-лист приходят уже согласованными: схема TaskCreate
    оставляет только пункты выбранного типа.
    """
    task = Task(
        title=data.title,
        contact=data.contact or None,
        due_date=data.due_date,
        description=data.description or None,
        assignee_id=data.assignee_id,
        card_type=data.card_type,
        status=DEFAULT_STATUS,
        checklist=dict(data.checklist),
        created_by=created_by,
    )
    task.position = await _next_position(db, DEFAULT_STATUS)
    db.add(task)
    await db.commit()
    # Перечитываем карточку: связи нужны сразу после создания
    created = await get_task(db, task.id)
    return created if created is not None else task


async def update_task(db: AsyncSession, task: Task, data: TaskUpdate) -> Task:
    """Меняет поля карточки; столбец — только если сняли исполнителя.

    Форма правки столбец не присылает: карточка остаётся на месте. Исключение —
    «Не выбран» в поле «Выполняет»: карточка без исполнителя не стоит в работе,
    поэтому после сохранения возвращается в «На очереди» так же, как её
    возвращает перетаскивание (move_task ставит её на место по сроку).
    Перемещение по доске идёт через move_task.
    """
    task.title = data.title
    task.contact = data.contact or None
    task.due_date = data.due_date
    task.description = data.description or None
    task.assignee_id = data.assignee_id
    task.card_type = data.card_type
    task.checklist = dict(data.checklist)
    status = data.status or task.status
    position = data.position
    if task.assignee_id is None and status != DEFAULT_STATUS:
        # Исполнителя нет — работа не начата: карточку возвращаем в «На очереди».
        # Место в столбце определит сортировка по сроку (move_task), поэтому
        # позицию, пришедшую вместе со столбцом, не переносим
        status = DEFAULT_STATUS
        position = None
    if status != task.status or position is not None:
        if position is None:
            position = len(await _column_tasks(db, status, exclude_id=task.id))
        return await move_task(db, task, status=status, position=position)
    await db.commit()
    updated = await get_task(db, task.id)
    return updated if updated is not None else task


async def move_task(
    db: AsyncSession,
    task: Task,
    *,
    status: TaskStatus,
    position: int,
    actor_id: int | None = None,
) -> Task:
    """Переносит карточку в столбец status на место position.

    Позиции в исходном и целевом столбцах перенумеровываются подряд (0..n-1),
    чтобы в порядке не появлялись дырки после каждого перетаскивания.

    Если карточку перенесли в другой столбец, целевой столбец сортируется
    по сроку по возрастанию (_due_sort_key): доска показывает карточки именно
    в этом порядке, поэтому место, куда её бросили, значения не имеет. При
    перестановке внутри столбца ручной порядок сохраняется.

    Если карточку вытащили из «На очереди» (DEFAULT_STATUS) в другой столбец
    и исполнитель ещё не указан, им становится сотрудник, который её
    перетащил (actor_id): работу начал он. Уже выбранного исполнителя перенос
    не меняет — ни в «На очереди», ни при перестановках между остальными
    столбцами.
    """
    old_status = task.status
    column_changed = old_status != status
    target = await _column_tasks(db, status, exclude_id=task.id)
    source = await _column_tasks(db, old_status, exclude_id=task.id) if column_changed else []

    task.status = status
    moved_out_of_queue = old_status == DEFAULT_STATUS and status != DEFAULT_STATUS
    reassigned = moved_out_of_queue and actor_id is not None and task.assignee_id is None
    if reassigned:
        task.assignee_id = actor_id
    target.insert(max(0, min(position, len(target))), task)
    if column_changed:
        # Столбец, куда перенесли карточку, выстраивается по сроку по возрастанию
        # (тот же порядок, что отдаёт list_board): без срока — в конце, при
        # одинаковых сроках остаётся место, куда карточку бросили (сортировка
        # стабильная). Перестановка внутри столбца ручной порядок не меняет.
        target.sort(key=_due_sort_key)
    for order, item in enumerate(target):
        item.position = order
    for order, item in enumerate(source):
        item.position = order

    await db.commit()
    if reassigned:
        # Связь assignee кэширована в объекте (expire_on_commit=False): после
        # смены ключа её нужно перечитать, иначе имя исполнителя осталось бы
        # прежним до нового запроса к БД
        await db.refresh(task, ["assignee"])
    moved = await get_task(db, task.id)
    return moved if moved is not None else task


async def archive_task(db: AsyncSession, task: Task) -> Task:
    """Убирает карточку в корзину: строка остаётся в БД с временем удаления."""
    task.deleted_at = _now()
    await db.commit()
    await db.refresh(task)
    return task


async def restore_task(db: AsyncSession, task: Task) -> Task:
    """Возвращает карточку из корзины в конец её столбца."""
    # Позицию считаем до сброса deleted_at: иначе карточка попадёт в выборку
    # как живая, получит место за самой собой и оставит дырку в конце столбца
    task.position = await _next_position(db, task.status)
    task.deleted_at = None
    await db.commit()
    await db.refresh(task)
    return task


async def purge_task(db: AsyncSession, task: Task) -> None:
    """Удаляет карточку из корзины окончательно, без возможности восстановления."""
    await db.delete(task)
    await db.commit()
