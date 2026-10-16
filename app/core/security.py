"""Криптография и токены: хеширование паролей, JWT и параметры cookie."""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

# Имя httpOnly-cookie, в которой лежит access-токен
TOKEN_COOKIE_NAME = "portal_token"

# Алгоритм подписи JWT
JWT_ALGORITHM = "HS256"

# Границы длины пароля (используются и в схемах валидации)
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128

# Контекст хеширования паролей (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class InvalidTokenError(Exception):
    """Токен отсутствует, просрочен или подпись не совпадает."""


def hash_password(password: str) -> str:
    """Возвращает хеш пароля для хранения в БД."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Сверяет пароль с хешем; повреждённый хеш совпадением не считается."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        return False


def create_access_token(*, subject: str, role: str) -> str:
    """Подписывает access-токен: в sub лежит идентификатор пользователя."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Проверяет подпись и срок действия токена, возвращает payload."""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise InvalidTokenError("Токен недействителен") from exc


def cookie_settings() -> dict[str, Any]:
    """Параметры cookie с токеном: httpOnly, SameSite=Lax, срок жизни токена."""
    settings = get_settings()
    return {
        "httponly": True,
        "samesite": "lax",
        "max_age": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "path": "/",
    }
