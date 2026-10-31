"""Маршруты раздела «Настройки»: разделы портала и управление пользователями.

Доступ к разделу открыт только нотариусу (роль ``admin``): сотрудникам
пункт меню не показывается, а прямой запрос адреса завершается отказом.
"""
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.core.templating import render
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import DEFAULT_MARKER_COLOR, User
from app.modules.auth.schemas import AdminUserUpdate, UserCreate, name_key
from app.modules.auth.service import (
    create_user,
    delete_user,
    get_user_by_id,
    get_user_by_name,
    list_users,
    set_marker_color,
    update_user,
)
from app.modules.google_calendar import service as google_calendar
from app.modules.settings.models import InheritanceTariff
from app.modules.settings.schemas import InheritanceTariffInput
from app.modules.settings.service import (
    create_inheritance_tariff,
    delete_inheritance_tariff,
    get_inheritance_tariff,
    list_inheritance_tariffs,
    update_inheritance_tariff,
)

router = APIRouter(tags=["settings"])

# Текущий пользователь с ролью нотариуса (администратора портала)
AdminUser = Annotated[User, Depends(require_role("admin"))]

# Значение active_menu для подсветки пункта «Настройки» в левом меню
MENU_SETTINGS = "settings"

# Выбранный раздел в меню самой страницы настроек
SETTINGS_USERS = "users"
SETTINGS_INHERITANCE_TARIFF = "inheritance_tariff"
SETTINGS_GOOGLE_CALENDAR = "google_calendar"

# Адреса действий раздела «Связь с Google Календарём»
GOOGLE_CALENDAR_URL = "/settings/google-calendar"


def _render_settings(
    request: Request,
    user: User,
    *,
    settings_section: str | None = None,
    users: list[User] | None = None,
    edit_user: User | None = None,
    tariffs: list[InheritanceTariff] | None = None,
    edit_tariff: InheritanceTariff | None = None,
    error: str | None = None,
    created: bool = False,
    updated: bool = False,
    deleted: bool = False,
    google_status: google_calendar.GoogleCalendarStatus | None = None,
    google_connect: dict[str, Any] | None = None,
    google_event: dict[str, str] | None = None,
    google_local: bool = True,
    google_local_url: str = GOOGLE_CALENDAR_URL,
    google_uploaded: bool = False,
    google_deleted: bool = False,
    google_disconnected: bool = False,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит страницу настроек с выбранным разделом справа от меню."""
    return render(
        request,
        "settings/index.html",
        user=user,
        active_menu=MENU_SETTINGS,
        settings_section=settings_section,
        users=users or [],
        edit_user=edit_user,
        tariffs=tariffs or [],
        edit_tariff=edit_tariff,
        error=error,
        created=created,
        updated=updated,
        deleted=deleted,
        users_url="/settings/users",
        create_url="/settings/users",
        default_marker_color=DEFAULT_MARKER_COLOR,
        google_status=google_status,
        google_url=GOOGLE_CALENDAR_URL,
        google_connect=google_connect,
        google_event=google_event,
        google_local=google_local,
        google_local_url=google_local_url,
        google_uploaded=google_uploaded,
        google_deleted=google_deleted,
        google_disconnected=google_disconnected,
        status_code=status_code,
    )


def _validation_message(exc: ValidationError) -> str:
    """Возвращает первое сообщение об ошибке валидации в читаемом виде."""
    message = str(exc.errors()[0].get("msg", "Некорректные данные"))
    return message.removeprefix("Value error, ")


async def _render_users_section(
    request: Request,
    db: AsyncSession,
    user: User,
    *,
    error: str | None = None,
    edit_user: User | None = None,
    created: bool = False,
    updated: bool = False,
    deleted: bool = False,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит раздел «Пользователи» в настройках с актуальным списком сотрудников."""
    return _render_settings(
        request,
        user,
        settings_section=SETTINGS_USERS,
        users=await list_users(db),
        edit_user=edit_user,
        error=error,
        created=created,
        updated=updated,
        deleted=deleted,
        status_code=status_code,
    )


async def _render_tariffs_section(
    request: Request,
    db: AsyncSession,
    user: User,
    *,
    error: str | None = None,
    edit_tariff: InheritanceTariff | None = None,
    created: bool = False,
    updated: bool = False,
    deleted: bool = False,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит раздел «Региональный тариф для наследства» с актуальным списком строк."""
    return _render_settings(
        request,
        user,
        settings_section=SETTINGS_INHERITANCE_TARIFF,
        tariffs=await list_inheritance_tariffs(db),
        edit_tariff=edit_tariff,
        error=error,
        created=created,
        updated=updated,
        deleted=deleted,
        status_code=status_code,
    )


@router.get("/settings", response_class=HTMLResponse, response_model=None)
async def settings_page(request: Request, user: AdminUser) -> HTMLResponse:
    """Страница «Настройки»: меню разделов настроек портала."""
    return _render_settings(request, user)


@router.get("/settings/users", response_class=HTMLResponse, response_model=None)
async def settings_users_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
    created: bool = False,
    updated: bool = False,
    deleted: bool = False,
    edit: int | None = None,
) -> HTMLResponse:
    """Список сотрудников внутри настроек: добавление, правка и удаление."""
    edit_user = await get_user_by_id(db, edit) if edit is not None else None
    if edit is not None and edit_user is None:
        # Ссылка устарела: сотрудник уже удалён
        return await _render_users_section(
            request,
            db,
            user,
            error="Пользователь для изменения не найден",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return await _render_users_section(
        request,
        db,
        user,
        edit_user=edit_user,
        created=created,
        updated=updated,
        deleted=deleted,
    )


@router.post("/settings/users", response_class=HTMLResponse, response_model=None)
async def settings_users_create(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
    full_name: Annotated[str, Form()],
    password: Annotated[str, Form()],
    role: Annotated[str, Form()] = "user",
    marker_color: Annotated[str, Form()] = DEFAULT_MARKER_COLOR,
) -> HTMLResponse | RedirectResponse:
    """Добавляет сотрудника, оставаясь в разделе настроек после успеха."""
    try:
        data = UserCreate(
            full_name=full_name, password=password, role=role, marker_color=marker_color
        )
    except ValidationError as exc:
        return await _render_users_section(
            request,
            db,
            user,
            error=_validation_message(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if await get_user_by_name(db, data.full_name) is not None:
        return await _render_users_section(
            request,
            db,
            user,
            error=f"Пользователь с именем «{data.full_name}» уже существует",
            status_code=status.HTTP_409_CONFLICT,
        )

    try:
        await create_user(db, data)
    except IntegrityError:
        # Страховка от гонки, если одинаковое имя добавляют одновременно
        await db.rollback()
        return await _render_users_section(
            request,
            db,
            user,
            error=f"Пользователь с именем «{data.full_name}» уже существует",
            status_code=status.HTTP_409_CONFLICT,
        )

    return RedirectResponse("/settings/users?created=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/users/{user_id}/update", response_class=HTMLResponse, response_model=None)
async def settings_users_update(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
    user_id: int,
    full_name: Annotated[str, Form()],
    password: Annotated[str, Form()] = "",
    marker_color: Annotated[str, Form()] = DEFAULT_MARKER_COLOR,
) -> HTMLResponse | RedirectResponse:
    """Сохраняет правку сотрудника и возвращает в список внутри настроек."""
    target = await get_user_by_id(db, user_id)
    if target is None:
        return await _render_users_section(
            request,
            db,
            user,
            error="Пользователь не найден",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    try:
        data = AdminUserUpdate(
            full_name=full_name, password=password, marker_color=marker_color
        )
    except ValidationError as exc:
        return await _render_users_section(
            request,
            db,
            user,
            edit_user=target,
            error=_validation_message(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if name_key(data.full_name) != target.name_key:
        existing = await get_user_by_name(db, data.full_name)
        if existing is not None and existing.id != target.id:
            return await _render_users_section(
                request,
                db,
                user,
                edit_user=target,
                error=f"Имя «{data.full_name}» уже занято другим пользователем",
                status_code=status.HTTP_409_CONFLICT,
            )

    try:
        await update_user(db, target, full_name=data.full_name, password=data.password)
        if target.marker_color != data.marker_color:
            await set_marker_color(db, target, data.marker_color)
    except IntegrityError:
        # Страховка от гонки, если то же имя занял другой сотрудник
        await db.rollback()
        return await _render_users_section(
            request,
            db,
            user,
            edit_user=await get_user_by_id(db, user_id),
            error=f"Имя «{data.full_name}» уже занято другим пользователем",
            status_code=status.HTTP_409_CONFLICT,
        )

    return RedirectResponse("/settings/users?updated=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/users/{user_id}/delete", response_class=HTMLResponse, response_model=None)
async def settings_users_delete(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
    user_id: int,
) -> HTMLResponse | RedirectResponse:
    """Удаляет сотрудника и возвращает в список внутри настроек."""
    if user_id == user.id:
        return await _render_users_section(
            request,
            db,
            user,
            error="Нельзя удалить собственную учётную запись",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    target = await get_user_by_id(db, user_id)
    if target is None:
        return await _render_users_section(
            request,
            db,
            user,
            error="Пользователь не найден",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    await delete_user(db, target)
    return RedirectResponse("/settings/users?deleted=1", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/settings/inheritance-tariff", response_class=HTMLResponse, response_model=None)
async def settings_inheritance_tariff_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
    created: bool = False,
    updated: bool = False,
    deleted: bool = False,
    edit: int | None = None,
) -> HTMLResponse:
    """Список региональных тарифов внутри настроек: добавление, правка и удаление."""
    edit_tariff = await get_inheritance_tariff(db, edit) if edit is not None else None
    if edit is not None and edit_tariff is None:
        # Ссылка устарела: строку уже удалили
        return await _render_tariffs_section(
            request,
            db,
            user,
            error="Строка для изменения не найдена",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return await _render_tariffs_section(
        request,
        db,
        user,
        edit_tariff=edit_tariff,
        created=created,
        updated=updated,
        deleted=deleted,
    )


@router.post("/settings/inheritance-tariff", response_class=HTMLResponse, response_model=None)
async def settings_inheritance_tariff_create(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
    asset_type: Annotated[str, Form()],
    rate: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    """Добавляет строку регионального тарифа и возвращает в раздел настроек."""
    try:
        data = InheritanceTariffInput(asset_type=asset_type, rate=rate)
    except ValidationError as exc:
        return await _render_tariffs_section(
            request,
            db,
            user,
            error=_validation_message(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    await create_inheritance_tariff(db, data)
    return RedirectResponse(
        "/settings/inheritance-tariff?created=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/settings/inheritance-tariff/{tariff_id}/update",
    response_class=HTMLResponse,
    response_model=None,
)
async def settings_inheritance_tariff_update(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
    tariff_id: int,
    asset_type: Annotated[str, Form()],
    rate: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    """Сохраняет правку строки регионального тарифа."""
    target = await get_inheritance_tariff(db, tariff_id)
    if target is None:
        return await _render_tariffs_section(
            request,
            db,
            user,
            error="Строка тарифа не найдена",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    try:
        data = InheritanceTariffInput(asset_type=asset_type, rate=rate)
    except ValidationError as exc:
        return await _render_tariffs_section(
            request,
            db,
            user,
            edit_tariff=target,
            error=_validation_message(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    await update_inheritance_tariff(db, target, data)
    return RedirectResponse(
        "/settings/inheritance-tariff?updated=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/settings/inheritance-tariff/{tariff_id}/delete",
    response_class=HTMLResponse,
    response_model=None,
)
async def settings_inheritance_tariff_delete(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
    tariff_id: int,
) -> HTMLResponse | RedirectResponse:
    """Удаляет строку регионального тарифа и возвращает в раздел настроек."""
    target = await get_inheritance_tariff(db, tariff_id)
    if target is None:
        return await _render_tariffs_section(
            request,
            db,
            user,
            error="Строка тарифа не найдена",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    await delete_inheritance_tariff(db, target)
    return RedirectResponse(
        "/settings/inheritance-tariff?deleted=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _local_calendar_url(request: Request) -> str:
    """Адрес раздела настроек на самом сервере портала (loopback для Google)."""
    port = request.url.port
    host = f"localhost:{port}" if port else "localhost"
    return f"http://{host}{GOOGLE_CALENDAR_URL}"


async def _render_google_calendar_section(
    request: Request,
    user: User,
    *,
    error: str | None = None,
    uploaded: bool = False,
    deleted: bool = False,
    disconnected: bool = False,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит раздел «Связь с Google Календарём» с текущим состоянием связи.

    Проверка токена и обращение к Google блокирующие, поэтому выполняются в
    пуле потоков: страница настроек не должна останавливать другие запросы.
    """
    status_info = await run_in_threadpool(google_calendar.get_status)
    connect = await run_in_threadpool(google_calendar.connect_state)
    last_event = await run_in_threadpool(google_calendar.last_test_event)
    return _render_settings(
        request,
        user,
        settings_section=SETTINGS_GOOGLE_CALENDAR,
        error=error,
        google_status=status_info,
        google_connect=connect,
        google_event=last_event,
        google_local=google_calendar.is_loopback_host(request.url.hostname),
        google_local_url=_local_calendar_url(request),
        google_uploaded=uploaded,
        google_deleted=deleted,
        google_disconnected=disconnected,
        status_code=status_code,
    )


@router.get("/settings/google-calendar", response_class=HTMLResponse, response_model=None)
async def settings_google_calendar_page(
    request: Request,
    user: AdminUser,
    uploaded: bool = False,
    deleted: bool = False,
    disconnected: bool = False,
) -> HTMLResponse:
    """Раздел «Связь с Google Календарём»: ключ, подключение и проверка событием."""
    return await _render_google_calendar_section(
        request,
        user,
        uploaded=uploaded,
        deleted=deleted,
        disconnected=disconnected,
    )


@router.post(
    "/settings/google-calendar/credentials",
    response_class=HTMLResponse,
    response_model=None,
)
async def settings_google_calendar_upload_credentials(
    request: Request,
    user: AdminUser,
    credentials: Annotated[UploadFile | None, File()] = None,
) -> HTMLResponse | RedirectResponse:
    """Сохраняет загруженный ключ OAuth-клиента и сбрасывает прежний токен."""
    if credentials is None:
        return await _render_google_calendar_section(
            request,
            user,
            error="Файл ключа не выбран",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Читаем на байт больше предела: так видно, что файл превышает допустимый размер
    raw = await credentials.read(google_calendar.MAX_CREDENTIALS_SIZE + 1)
    error = await run_in_threadpool(google_calendar.save_credentials, raw)
    if error:
        return await _render_google_calendar_section(
            request,
            user,
            error=error,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(
        f"{GOOGLE_CALENDAR_URL}?uploaded=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/settings/google-calendar/credentials/delete", response_model=None)
async def settings_google_calendar_delete_credentials(
    request: Request,
    user: AdminUser,
) -> RedirectResponse:
    """Удаляет ключ OAuth-клиента вместе с токеном: связь разрывается полностью."""
    await run_in_threadpool(google_calendar.delete_credentials)
    return RedirectResponse(
        f"{GOOGLE_CALENDAR_URL}?deleted=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/settings/google-calendar/connect",
    response_class=HTMLResponse,
    response_model=None,
)
async def settings_google_calendar_connect(
    request: Request,
    user: AdminUser,
) -> HTMLResponse | RedirectResponse:
    """Запускает вход в Google на компьютере, где запущен портал.

    Google принимает код подтверждения только на loopback-адресе сервера,
    поэтому с других компьютеров сети вход недоступен — им доступны статус,
    проверка и создание событий по уже сохранённому токену.
    """
    if not google_calendar.is_loopback_host(request.url.hostname):
        return await _render_google_calendar_section(
            request,
            user,
            error=(
                "Вход в Google выполняется только на компьютере с порталом: "
                f"откройте {_local_calendar_url(request)} и нажмите «Подключить календарь». "
                "С остальных компьютеров сети доступны статус, проверка и создание событий."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    error = await run_in_threadpool(google_calendar.start_connect)
    if error:
        return await _render_google_calendar_section(
            request,
            user,
            error=error,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(GOOGLE_CALENDAR_URL, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/settings/google-calendar/connect/status", response_model=None)
async def settings_google_calendar_connect_status(user: AdminUser) -> JSONResponse:
    """Состояние фонового входа в Google — его опрашивает страница настроек."""
    return JSONResponse(await run_in_threadpool(google_calendar.connect_state))


@router.post("/settings/google-calendar/disconnect", response_model=None)
async def settings_google_calendar_disconnect(
    request: Request,
    user: AdminUser,
) -> RedirectResponse:
    """Забывает токен доступа, оставляя загруженный ключ OAuth-клиента."""
    await run_in_threadpool(google_calendar.disconnect)
    return RedirectResponse(
        f"{GOOGLE_CALENDAR_URL}?disconnected=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/settings/google-calendar/test-event",
    response_class=HTMLResponse,
    response_model=None,
)
async def settings_google_calendar_test_event(
    request: Request,
    user: AdminUser,
) -> HTMLResponse | RedirectResponse:
    """Создаёт тестовое событие в календаре: проверка связи без макетов."""
    try:
        await run_in_threadpool(google_calendar.create_test_event)
    except google_calendar.GoogleCalendarError as exc:
        return await _render_google_calendar_section(
            request,
            user,
            error=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(GOOGLE_CALENDAR_URL, status_code=status.HTTP_303_SEE_OTHER)
