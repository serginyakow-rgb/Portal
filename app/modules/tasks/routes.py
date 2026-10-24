"""Маршруты модуля «Задачи»: доска, формы карточки, перемещение и корзина.

Префикс адресов (/tasks) задаётся при подключении роутера в app/main.py,
поэтому внутри модуля пути указаны без префикса.
"""
import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.core.templating import render
from app.modules.auth.dependencies import CurrentUser
from app.modules.auth.models import User
from app.modules.auth.service import list_users
from app.modules.google_calendar import service as google_calendar
from app.modules.tasks.schemas import (
    CARD_TYPE_CHECKLISTS,
    CARD_TYPE_LABELS,
    DEFAULT_CARD_TYPE,
    STATUS_CLASSES,
    STATUS_LABELS,
    STATUS_ORDER,
    TaskCreate,
    TaskMove,
    TaskMoveResult,
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

logger = logging.getLogger(__name__)

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


def _filter_assignee(value: str | None) -> int | None:
    """Исполнитель из фильтра доски; пустое значение — все сотрудники.

    Значение приходит из адреса строкой: пустой пункт списка («Все
    сотрудники») раньше попадал в int-параметр FastAPI, и доска отвечала
    ошибкой 422 int_parsing вместо всех карточек. Мусор в адресе тоже
    считаем отсутствием фильтра.
    """
    try:
        return int(value) if value and value.strip() else None
    except (TypeError, ValueError):
        return None


def _checked_items(names: list[str] | None) -> dict[str, bool]:
    """Отмеченные пункты чек-листа: чужие для типа пункты отбросит схема."""
    return {name: True for name in names or []}


async def _render_board(
    request: Request,
    db: AsyncSession,
    user: User,
    *,
    assignee_id: int | None = None,
    query: str = "",
    saved: bool = False,
    deleted: bool = False,
    gcal: str = "",
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит доску: столбцы и фильтр по исполнителю.

    Выбранный сотрудник показывает свои карточки и карточки без исполнителя
    (см. list_board); пустой фильтр — вся доска.
    """
    users = await list_users(db)
    # Неизвестный фильтр (сотрудника удалили) сбрасываем: доска показывается целиком
    if assignee_id is not None and all(employee.id != assignee_id for employee in users):
        assignee_id = None
    tasks = await list_board(db, assignee_id=assignee_id, query=query)
    return render(
        request,
        "tasks/index.html",
        user=user,
        active_menu=MENU_TASKS,
        columns=group_by_status(tasks),
        status_labels=STATUS_LABELS,
        status_order=STATUS_ORDER,
        status_classes=STATUS_CLASSES,
        today=date.today(),
        users=users,
        assignee_id=assignee_id,
        query=query,
        card_types=CARD_TYPE_LABELS,
        checklists=CARD_TYPE_CHECKLISTS,
        default_card_type=DEFAULT_CARD_TYPE,
        # Блок «Добавить в Google календарь» в модальном окне: только при
        # настроенной связи (Настройки → Связь с Google Календарём)
        google_calendar_connected=google_calendar.is_connected(),
        # Время события по умолчанию — то же, что подставит TaskCreate
        goog_cal_time=google_calendar.DEFAULT_EVENT_TIME,
        saved=saved,
        deleted=deleted,
        gcal=gcal,
        error=error,
        status_code=status_code,
    )


async def _render_trash(
    request: Request,
    db: AsyncSession,
    user: User,
    *,
    restored: bool = False,
    purged: bool = False,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит страницу корзины: удалённые карточки, возврат и удаление."""
    return render(
        request,
        "tasks/trash.html",
        user=user,
        active_menu=MENU_TASKS,
        trash=await list_trash(db),
        trash_count=await count_trash(db),
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
    goog_cal: bool = False,
    goog_cal_time: str = google_calendar.DEFAULT_EVENT_TIME,
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
        # Блок «Добавить в Google календарь» рядом со «Сроком» (см. _render_board).
        # Отметка и время возвращаются в форму, если карточку не удалось сохранить
        google_calendar_connected=google_calendar.is_connected(),
        goog_cal=goog_cal,
        goog_cal_time=goog_cal_time,
        error=error,
        status_code=status_code,
    )


@router.get("/", response_class=HTMLResponse, response_model=None)
async def index_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    assignee: str | None = None,
    q: str = "",
    saved: bool = False,
    deleted: bool = False,
    gcal: str = "",
) -> HTMLResponse:
    """Доска задач: четыре столбца и фильтры (исполнитель и поиск).

    «Все сотрудники» (пустой `?assignee=`) — вся доска; конкретный
    сотрудник — его карточки и карточки без исполнителя.

    При входе в раздел (адрес без параметров, например пункт меню «Задачи»)
    в фильтре «Исполнитель» подставляется текущий сотрудник: доска сразу
    показывает его карточки и карточки без исполнителя. Туда же ведёт кнопка
    «Сброс» — она очищает поиск и возвращает фильтр к текущему сотруднику.
    Переходы после действий (`?saved=`, `?deleted=`, `?gcal=`) и поиск (`?q=`)
    фильтр не подставляют — на экране остаётся то, что записано в адресе.
    """
    # «Вход в раздел» — адрес без параметров: подставляем авторизованного
    # сотрудника. Пустой `?assignee=` (пункт «Все сотрудники») и любой
    # другой параметр означают осознанный выбор — адрес не переписываем.
    if assignee is None and not any((q, saved, deleted, gcal)):
        assignee_id = user.id
    else:
        assignee_id = _filter_assignee(assignee)
    return await _render_board(
        request,
        db,
        user,
        assignee_id=assignee_id,
        query=q,
        saved=saved,
        deleted=deleted,
        gcal=gcal,
    )


@router.get("/trash", response_class=HTMLResponse, response_model=None)
async def trash_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    restored: bool = False,
    purged: bool = False,
) -> HTMLResponse:
    """Корзина: удалённые карточки, возврат на доску и окончательное удаление."""
    return await _render_trash(request, db, user, restored=restored, purged=purged)


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
    goog_cal: Annotated[str, Form(alias="GoogCal")] = "",
    goog_cal_time: Annotated[str, Form(alias="GoogCalTime")] = google_calendar.DEFAULT_EVENT_TIME,
) -> HTMLResponse | RedirectResponse:
    """Создаёт карточку: она встаёт в конец столбца «На очереди».

    Если отмечен чекбокс «Добавить в Google календарь», после сохранения
    карточки создаётся событие: заголовок — из «Заголовка карточки», дата —
    из «Срока», время — из поля времени. Сбой календаря карточку не отменяет:
    она уже записана, а на доске появляется предупреждение.
    """
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
            goog_cal=bool(goog_cal),
            goog_cal_time=goog_cal_time,
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
            goog_cal=bool(goog_cal),
            goog_cal_time=goog_cal_time,
            error="Выбранный исполнитель не найден",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    await create_task(db, data, created_by=user.id)

    # Отметка «Добавить в Google календарь»: событие создаётся после записи
    # карточки, чтобы сбой календаря не отменял уже введённые данные
    if not goog_cal:
        return RedirectResponse("/tasks/?saved=1", status_code=status.HTTP_303_SEE_OTHER)

    # Без срока событию некуда встать — карточка сохранена, событие пропущено
    if data.due_date is None:
        return RedirectResponse(
            "/tasks/?saved=1&gcal=no_date", status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        # Google отвечает секундами: запрос уходит в пул потоков, чтобы доска
        # и остальные страницы портала не ждали календарь (как в настройках)
        event = await run_in_threadpool(
            google_calendar.create_task_event,
            data.title,
            data.due_date,
            goog_cal_time,
        )
    except google_calendar.GoogleCalendarError as exc:
        logger.warning("Событие карточки «%s» не создано: %s", data.title, exc)
        return RedirectResponse(
            "/tasks/?saved=1&gcal=failed", status_code=status.HTTP_303_SEE_OTHER
        )

    logger.info("Событие карточки «%s» создано: %s", data.title, event["html_link"])
    return RedirectResponse(
        "/tasks/?saved=1&gcal=created", status_code=status.HTTP_303_SEE_OTHER
    )


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
        return await _render_trash(
            request,
            db,
            user,
            error="Карточка не найдена",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if task.deleted_at is not None:
        await restore_task(db, task)
    return RedirectResponse("/tasks/trash?restored=1", status_code=status.HTTP_303_SEE_OTHER)


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
        return await _render_trash(
            request,
            db,
            user,
            error="Карточка не найдена",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if task.deleted_at is None:
        return await _render_trash(
            request,
            db,
            user,
            error="Удалить навсегда можно только карточку из корзины",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    await purge_task(db, task)
    return RedirectResponse("/tasks/trash?purged=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/move/{task_id}", response_model=TaskMoveResult)
async def task_move(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    task_id: int,
    payload: TaskMove,
) -> TaskMoveResult:
    """Переносит карточку по доске: короткий ответ для перетаскивания без перезагрузки.

    Параметр user — зависимость авторизации: перемещать может только вошедший
    сотрудник, отдельных прав на карточки у модуля нет. Если карточку вытащили
    из «На очереди», исполнителем становится этот сотрудник (move_task), поэтому
    в ответе возвращается исполнитель — доска обновляет его имя в карточке
    без перезагрузки.
    """
    task = await get_task(db, task_id)
    if task is None or task.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Карточка не найдена",
        )
    moved = await move_task(
        db,
        task,
        status=payload.status,
        position=payload.position,
        actor_id=user.id,
    )
    return TaskMoveResult(
        assignee_id=moved.assignee_id,
        assignee_name=moved.assignee.full_name if moved.assignee else None,
        assignee_color=moved.assignee.marker_color if moved.assignee else None,
    )
