"""Маршруты модуля «Задачи»: доска, формы карточки, перемещение и корзина.

Префикс адресов (/tasks) задаётся при подключении роутера в app/main.py,
поэтому внутри модуля пути указаны без префикса.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.templating import render
from app.modules.auth.dependencies import CurrentUser
from app.modules.auth.models import User
from app.modules.auth.service import list_users
from app.modules.tasks.schemas import (
    CARD_TYPE_CHECKLISTS,
    CARD_TYPE_LABELS,
    DEFAULT_CARD_TYPE,
    STATUS_LABELS,
    STATUS_ORDER,
    TaskCreate,
    TaskMove,
    TaskRead,
    TaskUpdate,
)
from app.modules.tasks.service import (
    archive_task,
    count_trash,
    create_task,
    get_task,
    group_by_status,
    list_board,
    list_trash,
    move_task,
    purge_task,
    read_task,
    restore_task,
    update_task,
)

router = APIRouter(tags=["tasks"])

# Значение active_menu для подсветки пункта «Задачи» в левом меню
MENU_TASKS = "tasks"


def _validation_message(exc: ValidationError) -> str:
    """Возвращает первое сообщение об ошибке валидации в читаемом виде."""
    message = str(exc.errors()[0].get("msg", "Некорректные данные"))
    return message.removeprefix("Value error, ")


def _to_int(value: str | None) -> int:
    """Число из поля формы; пустое или мусорное значение считается нулём."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _checked_items(names: list[str] | None) -> dict[str, bool]:
    """Отмеченные пункты чек-листа: чужие для типа пункты отбросит схема."""
    return {name: True for name in names or []}


async def _render_board(
    request: Request,
    db: AsyncSession,
    user: User,
    *,
    assignee_id: int | None = None,
    saved: bool = False,
    deleted: bool = False,
    restored: bool = False,
    purged: bool = False,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит доску: столбцы, фильтр по исполнителю и корзину."""
    users = await list_users(db)
    # Неизвестный фильтр (сотрудника удалили) сбрасываем: доска показывается целиком
    if assignee_id is not None and all(employee.id != assignee_id for employee in users):
        assignee_id = None
    tasks = await list_board(db, assignee_id=assignee_id)
    return render(
        request,
        "tasks/index.html",
        user=user,
        active_menu=MENU_TASKS,
        columns=group_by_status(tasks),
        status_labels=STATUS_LABELS,
        status_order=STATUS_ORDER,
        users=users,
        assignee_id=assignee_id,
        card_types=CARD_TYPE_LABELS,
        checklists=CARD_TYPE_CHECKLISTS,
        default_card_type=DEFAULT_CARD_TYPE,
        trash=await list_trash(db),
        trash_count=await count_trash(db),
        saved=saved,
        deleted=deleted,
        restored=restored,
        purged=purged,
        error=error,
        status_code=status_code,
    )


def _render_task_form(
    request: Request,
    user: User,
    *,
    users: list[User],
    task: TaskRead | None = None,
    title: str = "",
    contact: str = "",
    due_date: str = "",
    description: str = "",
    assignee_id: int | None = None,
    card_type: str = DEFAULT_CARD_TYPE,
    checklist: dict[str, bool] | None = None,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит форму карточки: создание и правку."""
    items = checklist if checklist is not None else {}
    return render(
        request,
        "tasks/form.html",
        user=user,
        active_menu=MENU_TASKS,
        users=users,
        task=task,
        title=title,
        contact=contact,
        due_date=due_date,
        description=description,
        assignee_id=assignee_id,
        card_type=card_type,
        checklist=items,
        card_types=CARD_TYPE_LABELS,
        checklists=CARD_TYPE_CHECKLISTS,
        status_labels=STATUS_LABELS,
        error=error,
        status_code=status_code,
    )


@router.get("/", response_class=HTMLResponse, response_model=None)
async def index_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    assignee: int | None = None,
    saved: bool = False,
    deleted: bool = False,
    restored: bool = False,
    purged: bool = False,
) -> HTMLResponse:
    """Доска задач: четыре столбца, фильтр по исполнителю и корзина."""
    return await _render_board(
        request,
        db,
        user,
        assignee_id=assignee,
        saved=saved,
        deleted=deleted,
        restored=restored,
        purged=purged,
    )


@router.get("/create", response_class=HTMLResponse, response_model=None)
async def task_create_form(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    card_type: str = "",
) -> HTMLResponse:
    """Форма новой карточки: тип можно задать заранее в адресе."""
    kind = card_type if card_type in CARD_TYPE_LABELS else DEFAULT_CARD_TYPE
    return _render_task_form(request, user, users=await list_users(db), card_type=kind)


@router.post("/create", response_class=HTMLResponse, response_model=None)
async def task_create(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    title: Annotated[str, Form()] = "",
    contact: Annotated[str, Form()] = "",
    due_date: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    assignee_id: Annotated[str, Form()] = "",
    card_type: Annotated[str, Form()] = "",
    checklist: Annotated[list[str] | None, Form()] = None,
) -> HTMLResponse | RedirectResponse:
    """Создаёт карточку: она встаёт в конец столбца «На очереди»."""
    users = await list_users(db)
    checked = _checked_items(checklist)
    try:
        data = TaskCreate(
            title=title,
            contact=contact,
            due_date=due_date,
            description=description,
            assignee_id=assignee_id,
            card_type=card_type or DEFAULT_CARD_TYPE,
            checklist=checked,
        )
    except ValidationError as exc:
        return _render_task_form(
            request,
            user,
            users=users,
            title=title,
            contact=contact,
            due_date=due_date,
            description=description,
            assignee_id=_to_int(assignee_id) or None,
            card_type=card_type or DEFAULT_CARD_TYPE,
            checklist=checked,
            error=_validation_message(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if data.assignee_id is not None and all(item.id != data.assignee_id for item in users):
        return _render_task_form(
            request,
            user,
            users=users,
            title=title,
            contact=contact,
            due_date=due_date,
            description=description,
            assignee_id=data.assignee_id,
            card_type=data.card_type,
            checklist=checked,
            error="Выбранный исполнитель не найден",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    await create_task(db, data, created_by=user.id)
    return RedirectResponse("/tasks/?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/update/{task_id}", response_class=HTMLResponse, response_model=None)
async def task_edit_form(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    task_id: int,
) -> HTMLResponse:
    """Форма правки карточки: заполняется текущими значениями."""
    task = await read_task(db, task_id)
    if task is None:
        return await _render_board(
            request,
            db,
            user,
            error="Карточка не найдена",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return _render_task_form(
        request,
        user,
        users=await list_users(db),
        task=task,
        title=task.title,
        contact=task.contact or "",
        due_date=task.due_date.isoformat() if task.due_date else "",
        description=task.description or "",
        assignee_id=task.assignee_id,
        card_type=task.card_type,
        checklist=task.checklist,
    )


@router.post("/update/{task_id}", response_class=HTMLResponse, response_model=None)
async def task_update(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    task_id: int,
    title: Annotated[str, Form()] = "",
    contact: Annotated[str, Form()] = "",
    due_date: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    assignee_id: Annotated[str, Form()] = "",
    card_type: Annotated[str, Form()] = "",
    checklist: Annotated[list[str] | None, Form()] = None,
) -> HTMLResponse | RedirectResponse:
    """Сохраняет поля карточки; столбец и позицию меняет только доска."""
    task = await get_task(db, task_id)
    if task is None:
        return await _render_board(
            request,
            db,
            user,
            error="Карточка не найдена",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    users = await list_users(db)
    checked = _checked_items(checklist)
    try:
        data = TaskUpdate(
            title=title,
            contact=contact,
            due_date=due_date,
            description=description,
            assignee_id=assignee_id,
            card_type=card_type or DEFAULT_CARD_TYPE,
            checklist=checked,
        )
    except ValidationError as exc:
        return _render_task_form(
            request,
            user,
            users=users,
            task=await read_task(db, task_id),
            title=title,
            contact=contact,
            due_date=due_date,
            description=description,
            assignee_id=_to_int(assignee_id) or None,
            card_type=card_type or DEFAULT_CARD_TYPE,
            checklist=checked,
            error=_validation_message(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if data.assignee_id is not None and all(item.id != data.assignee_id for item in users):
        return _render_task_form(
            request,
            user,
            users=users,
            task=await read_task(db, task_id),
            title=title,
            contact=contact,
            due_date=due_date,
            description=description,
            assignee_id=data.assignee_id,
            card_type=data.card_type,
            checklist=checked,
            error="Выбранный исполнитель не найден",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    await update_task(db, task, data)
    return RedirectResponse("/tasks/?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/delete/{task_id}", response_class=HTMLResponse, response_model=None)
async def task_delete(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    task_id: int,
) -> HTMLResponse | RedirectResponse:
    """Убирает карточку в корзину: восстановить можно со страницы корзины."""
    task = await get_task(db, task_id)
    if task is None:
        return await _render_board(
            request,
            db,
            user,
            error="Карточка не найдена",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if task.deleted_at is None:
        await archive_task(db, task)
    return RedirectResponse("/tasks/?deleted=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/restore/{task_id}", response_class=HTMLResponse, response_model=None)
async def task_restore(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    task_id: int,
) -> HTMLResponse | RedirectResponse:
    """Возвращает карточку из корзины в конец её столбца."""
    task = await get_task(db, task_id)
    if task is None:
        return await _render_board(
            request,
            db,
            user,
            error="Карточка не найдена",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if task.deleted_at is not None:
        await restore_task(db, task)
    return RedirectResponse("/tasks/?restored=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/purge/{task_id}", response_class=HTMLResponse, response_model=None)
async def task_purge(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    task_id: int,
) -> HTMLResponse | RedirectResponse:
    """Удаляет карточку из корзины окончательно: активную карточку не трогает."""
    task = await get_task(db, task_id)
    if task is None:
        return await _render_board(
            request,
            db,
            user,
            error="Карточка не найдена",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if task.deleted_at is None:
        return await _render_board(
            request,
            db,
            user,
            error="Удалить навсегда можно только карточку из корзины",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    await purge_task(db, task)
    return RedirectResponse("/tasks/?purged=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/move/{task_id}", response_model=None)
async def task_move(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    task_id: int,
    payload: TaskMove,
) -> dict[str, bool]:
    """Переносит карточку по доске: короткий ответ для перетаскивания без перезагрузки.

    Параметр user — зависимость авторизации: перемещать может только вошедший
    сотрудник, отдельных прав на карточки у модуля нет.
    """
    task = await get_task(db, task_id)
    if task is None or task.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Карточка не найдена",
        )
    await move_task(db, task, status=payload.status, position=payload.position)
    return {"ok": True}
