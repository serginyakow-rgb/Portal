"""Бизнес-логика модуля «Задачи»: доска, карточки, перемещение и корзина.

Модуль не импортирует модели других модулей: имя исполнителя берётся из
связи assignee (она загружается вместе с карточкой), а список сотрудников
для фильтра роуты получают из auth.service.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
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


def _to_list_item(task: Task) -> TaskListItem:
    """Карточка доски: подпись типа и имя исполнителя берутся из справочника и связи."""
    return TaskListItem(
        id=task.id,
        title=task.title,
        contact=task.contact,
        due_date=task.due_date,
        card_type=task.card_type,
        card_type_label=CARD_TYPE_LABELS.get(task.card_type, task.card_type),
        status=task.status,
        position=task.position,
        assignee_id=task.assignee_id,
        assignee_name=task.assignee.full_name if task.assignee else None,
        assignee_color=task.assignee.marker_color if task.assignee else None,
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
    """
    stmt = select(Task).where(Task.deleted_at.is_(None))
    if assignee_id is not None:
        stmt = stmt.where(Task.assignee_id == assignee_id)
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
    """Меняет поля карточки; столбец и позицию — только если они переданы явно.

    Форма правки столбец не присылает: карточка остаётся на месте. Перемещение
    по доске идёт через move_task.
    """
    task.title = data.title
    task.contact = data.contact or None
    task.due_date = data.due_date
    task.description = data.description or None
    task.assignee_id = data.assignee_id
    task.card_type = data.card_type
    task.checklist = dict(data.checklist)
    if data.status is not None or data.position is not None:
        status = data.status or task.status
        if data.position is None:
            position = len(await _column_tasks(db, status, exclude_id=task.id))
        else:
            position = data.position
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
) -> Task:
    """Переносит карточку в столбец status на место position.

    Позиции в исходном и целевом столбцах перенумеровываются подряд (0..n-1),
    чтобы в порядке не появлялись дырки после каждого перетаскивания.
    """
    old_status = task.status
    target = await _column_tasks(db, status, exclude_id=task.id)
    source = await _column_tasks(db, old_status, exclude_id=task.id) if old_status != status else []

    task.status = status
    target.insert(max(0, min(position, len(target))), task)
    for order, item in enumerate(target):
        item.position = order
    for order, item in enumerate(source):
        item.position = order

    await db.commit()
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
