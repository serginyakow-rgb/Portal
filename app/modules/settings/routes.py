"""Маршруты раздела «Настройки»: разделы портала и управление пользователями.

Доступ к разделу открыт только нотариусу (роль ``admin``): сотрудникам
пункт меню не показывается, а прямой запрос адреса завершается отказом.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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


@router.get("/settings/backup", response_class=HTMLResponse, response_model=None)
async def settings_backup_page(request: Request, user: AdminUser) -> HTMLResponse:
    """Заглушка раздела «Резервное копирование»: функционал появится позже."""
    return render(
        request,
        "settings/section.html",
        user=user,
        active_menu=MENU_SETTINGS,
        section_title="Резервное копирование",
    )


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
