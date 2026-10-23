"""Маршруты аутентификации: вход по имени и профиль сотрудника."""
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    TOKEN_COOKIE_NAME,
    cookie_settings,
    create_access_token,
    verify_password,
)
from app.core.templating import MENU_PROFILE, render
from app.modules.auth.dependencies import CurrentUser, OptionalUser
from app.modules.auth.models import DEFAULT_MARKER_COLOR, User
from app.modules.auth.schemas import LoginForm, PasswordChange, ProfileMarkerColor
from app.modules.auth.service import authenticate_user, set_marker_color, set_password

router = APIRouter(prefix="/auth", tags=["auth"])


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


def _render_profile(
    request: Request,
    user: User,
    *,
    error: str | None = None,
    updated: bool = False,
    color_updated: bool = False,
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
        color_updated=color_updated,
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


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request, user: CurrentUser, updated: bool = False, color: bool = False
) -> HTMLResponse:
    """Профиль сотрудника: имя меняет администратор, пароль и метку сотрудник — сам."""
    return _render_profile(request, user, updated=updated, color_updated=color)


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


@router.post("/profile/marker-color", response_class=HTMLResponse, response_model=None)
async def profile_marker_color_change(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    marker_color: Annotated[str, Form()] = DEFAULT_MARKER_COLOR,
) -> HTMLResponse | RedirectResponse:
    """Меняет цвет метки текущего сотрудника: им он отмечен в списках портала."""
    try:
        data = ProfileMarkerColor(marker_color=marker_color)
    except ValidationError as exc:
        return _render_profile(
            request,
            user,
            error=_validation_message(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Совпадающий цвет не переписываем: лишняя запись в БД сотруднику не нужна
    if user.marker_color != data.marker_color:
        await set_marker_color(db, user, data.marker_color)
    return RedirectResponse("/auth/profile?color=1", status_code=status.HTTP_303_SEE_OTHER)
