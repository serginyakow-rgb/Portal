"""Зависимости FastAPI: определение текущего пользователя и проверка роли."""
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TOKEN_COOKIE_NAME, InvalidTokenError, decode_access_token
from app.modules.auth.models import User
from app.modules.auth.service import get_user_by_id


async def _resolve_user(request: Request, db: AsyncSession) -> User | None:
    """Пытается определить пользователя по cookie; None — если сессии нет."""
    token = request.cookies.get(TOKEN_COOKIE_NAME)
    if not token:
        return None

    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        return None

    # В токене хранится только id: переименование пользователя не рвёт его сессию
    try:
        user_id = int(str(payload.get("sub")))
    except (TypeError, ValueError):
        return None

    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        return None
    return user


async def get_optional_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Для публичных страниц: пользователь может быть авторизован, а может и нет."""
    return await _resolve_user(request, db)


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Требует активную сессию, иначе отвечает 401."""
    user = await _resolve_user(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
        )
    return user


# Готовые аннотации для сигнатур маршрутов
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_role(role: str) -> Callable[..., Awaitable[User]]:
    """Возвращает зависимость, пропускающую только пользователей с нужной ролью."""

    async def dependency(user: CurrentUser) -> User:
        if user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для этого раздела",
            )
        return user

    return dependency
