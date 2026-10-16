"""Схемы (Pydantic) для пользователей портала и формы входа."""
import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.core.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH

# Имя пользователя — только русские буквы, пробел и дефис
NAME_PATTERN = re.compile(r"^[А-Яа-яЁё][А-Яа-яЁё\s-]*$")

# Поддерживаемые роли портала
ALLOWED_ROLES = {"admin", "user"}

# Границы длины имени (ФИО)
MIN_NAME_LENGTH = 2
MAX_NAME_LENGTH = 120


def name_key(full_name: str) -> str:
    """Ключ имени для поиска: регистр и повторные пробелы значения не имеют."""
    return " ".join(full_name.split()).casefold()


def _check_password_bounds(value: str) -> str:
    """Проверяет длину пароля: общее правило для входа, смены и правки администратором."""
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Пароль должен содержать минимум {MIN_PASSWORD_LENGTH} символов")
    if len(value) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Пароль слишком длинный (максимум {MAX_PASSWORD_LENGTH} символов)")
    return value


class _NameForm(BaseModel):
    """Общая валидация имени: кириллица, пробел и дефис, единый вид строки."""

    full_name: str = ""

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        """Схлопывает пробелы и проверяет, что имя написано по-русски."""
        cleaned = " ".join(value.split())
        if len(cleaned) < MIN_NAME_LENGTH:
            raise ValueError(f"Имя должно содержать минимум {MIN_NAME_LENGTH} символа")
        if len(cleaned) > MAX_NAME_LENGTH:
            raise ValueError(f"Имя слишком длинное (максимум {MAX_NAME_LENGTH} символов)")
        if not NAME_PATTERN.match(cleaned):
            raise ValueError("Имя может содержать только русские буквы, пробел и дефис")
        return cleaned


class LoginForm(_NameForm):
    """Данные формы входа в портал: имя на русском и пароль."""

    password: str = ""

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        """Проверяет длину пароля до обращения к хешу."""
        return _check_password_bounds(value)


class UserCreate(LoginForm):
    """Данные для добавления пользователя администратором."""

    role: str = "user"

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        """Разрешает только известные роли портала."""
        if value not in ALLOWED_ROLES:
            raise ValueError("Неизвестная роль пользователя")
        return value


class UserNameUpdate(_NameForm):
    """Смена имени пользователя: администратором в разделе «Пользователи»."""


class AdminUserUpdate(UserNameUpdate):
    """Правка сотрудника администратором: имя и, при необходимости, новый пароль."""

    password: str = ""

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        """Пустое значение означает «пароль не меняем», иначе проверяем длину."""
        if not value:
            return value
        return _check_password_bounds(value)


class PasswordChange(BaseModel):
    """Смена сотрудником собственного пароля с подтверждением."""

    current_password: str = ""
    new_password: str = ""
    new_password_repeat: str = ""

    @field_validator("current_password")
    @classmethod
    def validate_current_password(cls, value: str) -> str:
        """Текущий пароль обязателен: он подтверждает, что смену делает владелец учётной записи."""
        return _check_password_bounds(value)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        """Новый пароль проверяется по тем же границам длины."""
        return _check_password_bounds(value)

    @model_validator(mode="after")
    def validate_repeat(self) -> "PasswordChange":
        """Новый пароль и подтверждение должны совпадать."""
        if self.new_password != self.new_password_repeat:
            raise ValueError("Новый пароль и подтверждение не совпадают")
        return self


class UserRead(BaseModel):
    """Пользователь в API-ответах: ORM-объект сериализуется как есть."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    """JWT-токен, выданный после успешного входа."""

    access_token: str
    token_type: str = "bearer"
