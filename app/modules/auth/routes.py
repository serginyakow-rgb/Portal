"""Маршруты аутентификации: вход по имени, регистрация сотрудников и профиль."""
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    TOKEN_COOKIE_NAME,
    cookie_settings,
    create_access_token,
    verify_password,
)
from app.core.templating import MENU_PROFILE, MENU_USERS, render
from app.modules.auth.dependencies import CurrentUser, OptionalUser, require_role
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    AdminUserUpdate,
    LoginForm,
    PasswordChange,
    UserCreate,
    name_key,
)
from app.modules.auth.service import (
    authenticate_user,
    create_user,
    delete_user,
    get_user_by_id,
    get_user_by_name,
    list_users,
    set_password,
    update_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Текущий пользователь с ролью администратора (для раздела «Пользователи»)
AdminUser = Annotated[User, Depends(require_role("admin"))]


def _validation_message(exc: ValidationError) -> str:
    """Возвращает первое сообщение об ошибке валидации в читаемом виде."""
    message = str(exc.errors()[0].get("msg", "Некорректные данные"))
    return message.removeprefix("Value error, ")


def _render_login(
    request: Request,
    *,
    error: str | None = None,
    full_name: str = "",
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит страницу входа, сохраняя введённое имя при ошибке."""
    return render(
        request,
        "auth/login.html",
        user=None,
        full_name=full_name,
        error=error,
        status_code=status_code,
    )


async def _render_users_page(
    request: Request,
    db: AsyncSession,
    admin: User,
    *,
    error: str | None = None,
    created: bool = False,
    updated: bool = False,
    deleted: bool = False,
    edit_user: User | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит страницу управления пользователями с актуальным списком."""
    return render(
        request,
        "auth/users.html",
        user=admin,
        active_menu=MENU_USERS,
        users=await list_users(db),
        error=error,
        created=created,
        updated=updated,
        deleted=deleted,
        edit_user=edit_user,
        status_code=status_code,
    )


def _render_profile(
    request: Request,
    user: User,
    *,
    error: str | None = None,
    updated: bool = False,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит страницу профиля сотрудника."""
    return render(
        request,
        "auth/profile.html",
        user=user,
        active_menu=MENU_PROFILE,
        error=error,
        updated=updated,
        status_code=status_code,
    )


@router.get("/login", response_class=HTMLResponse, response_model=None)
async def login_form(request: Request, user: OptionalUser) -> HTMLResponse | RedirectResponse:
    """Страница входа; уже вошедшего сотрудника сразу отправляет на панель."""
    if user is not None:
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return _render_login(request)


@router.post("/login", response_class=HTMLResponse, response_model=None)
async def login(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    full_name: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    """Проверяет имя и пароль, ставит httpOnly-cookie с JWT и ведёт на панель."""
    try:
        form = LoginForm(full_name=full_name, password=password)
    except ValidationError as exc:
        return _render_login(
            request,
            error=_validation_message(exc),
            full_name=full_name,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user = await authenticate_user(db, form.full_name, form.password)
    if user is None:
        return _render_login(
            request,
            error="Неверное имя или пароль",
            full_name=form.full_name,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token = create_access_token(subject=str(user.id), role=user.role)
    response = RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(TOKEN_COOKIE_NAME, token, **cookie_settings())
    return response


@router.post("/logout")
async def logout() -> RedirectResponse:
    """Удаляет cookie с токеном и возвращает на страницу входа."""
    response = RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(TOKEN_COOKIE_NAME, path="/")
    return response


@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: AdminUser,
    created: bool = False,
    updated: bool = False,
    deleted: bool = False,
    edit: int | None = None,
) -> HTMLResponse:
    """Список пользователей портала, добавление сотрудника и правка выбранного."""
    edit_user = await get_user_by_id(db, edit) if edit is not None else None
    if edit is not None and edit_user is None:
        # Ссылка устарела: сотрудник уже удалён
        return await _render_users_page(
            request,
            db,
            admin,
            error="Пользователь для изменения не найден",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return await _render_users_page(
        request,
        db,
        admin,
        created=created,
        updated=updated,
        deleted=deleted,
        edit_user=edit_user,
    )


@router.post("/register", response_class=HTMLResponse, response_model=None)
async def register(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: AdminUser,
    full_name: Annotated[str, Form()],
    password: Annotated[str, Form()],
    role: Annotated[str, Form()] = "user",
) -> HTMLResponse | RedirectResponse:
    """Создаёт сотрудника с именем и паролем: вход будет выполняться по имени."""
    try:
        data = UserCreate(full_name=full_name, password=password, role=role)
    except ValidationError as exc:
        return await _render_users_page(
            request,
            db,
            admin,
            error=_validation_message(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if await get_user_by_name(db, data.full_name) is not None:
        return await _render_users_page(
            request,
            db,
            admin,
            error=f"Пользователь с именем «{data.full_name}» уже существует",
            status_code=status.HTTP_409_CONFLICT,
        )

    try:
        await create_user(db, data)
    except IntegrityError:
        # Страховка от гонки, если одинаковое имя добавляют одновременно
        await db.rollback()
        return await _render_users_page(
            request,
            db,
            admin,
            error=f"Пользователь с именем «{data.full_name}» уже существует",
            status_code=status.HTTP_409_CONFLICT,
        )

    return RedirectResponse("/auth/users?created=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/users/{user_id}/update", response_class=HTMLResponse, response_model=None)
async def users_update(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: AdminUser,
    user_id: int,
    full_name: Annotated[str, Form()],
    password: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Правка сотрудника администратором: имя и, при необходимости, новый пароль."""
    target = await get_user_by_id(db, user_id)
    if target is None:
        return await _render_users_page(
            request,
            db,
            admin,
            error="Пользователь не найден",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    try:
        data = AdminUserUpdate(full_name=full_name, password=password)
    except ValidationError as exc:
        return await _render_users_page(
            request,
            db,
            admin,
            error=_validation_message(exc),
            edit_user=target,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if name_key(data.full_name) != target.name_key:
        existing = await get_user_by_name(db, data.full_name)
        if existing is not None and existing.id != target.id:
            return await _render_users_page(
                request,
                db,
                admin,
                error=f"Имя «{data.full_name}» уже занято другим пользователем",
                edit_user=target,
                status_code=status.HTTP_409_CONFLICT,
            )

    try:
        await update_user(db, target, full_name=data.full_name, password=data.password)
    except IntegrityError:
        # Страховка от гонки, если то же имя занял другой сотрудник
        await db.rollback()
        return await _render_users_page(
            request,
            db,
            admin,
            error=f"Имя «{data.full_name}» уже занято другим пользователем",
            edit_user=target,
            status_code=status.HTTP_409_CONFLICT,
        )

    return RedirectResponse("/auth/users?updated=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/users/{user_id}/delete", response_class=HTMLResponse, response_model=None)
async def users_delete(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: AdminUser,
    user_id: int,
) -> HTMLResponse | RedirectResponse:
    """Удаляет сотрудника из портала: свою учётную запись удалить нельзя."""
    if user_id == admin.id:
        return await _render_users_page(
            request,
            db,
            admin,
            error="Нельзя удалить собственную учётную запись",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    target = await get_user_by_id(db, user_id)
    if target is None:
        return await _render_users_page(
            request,
            db,
            admin,
            error="Пользователь не найден",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    await delete_user(db, target)
    return RedirectResponse("/auth/users?deleted=1", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user: CurrentUser, updated: bool = False) -> HTMLResponse:
    """Профиль сотрудника: имя меняет администратор, себе сотрудник меняет только пароль."""
    return _render_profile(request, user, updated=updated)


@router.post("/profile/password", response_class=HTMLResponse, response_model=None)
async def profile_password_change(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    current_password: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    new_password_repeat: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    """Меняет пароль текущего сотрудника; выданный JWT продолжает действовать."""
    try:
        data = PasswordChange(
            current_password=current_password,
            new_password=new_password,
            new_password_repeat=new_password_repeat,
        )
    except ValidationError as exc:
        return _render_profile(
            request,
            user,
            error=_validation_message(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not verify_password(data.current_password, user.hashed_password):
        return _render_profile(
            request,
            user,
            error="Текущий пароль указан неверно",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    await set_password(db, user, data.new_password)
    return RedirectResponse("/auth/profile?updated=1", status_code=status.HTTP_303_SEE_OTHER)
