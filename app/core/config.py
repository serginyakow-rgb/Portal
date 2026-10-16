"""Настройки приложения: читаются из .env через pydantic-settings."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация портала, загружаемая из переменных окружения."""

    # Секрет для подписи JWT — обязательно заменить в рабочем окружении
    SECRET_KEY: str = "dev-secret-change-me"
    # Строка подключения к БД (асинхронный драйвер; SQLite -> позже PostgreSQL)
    DATABASE_URL: str = "sqlite+aiosqlite:///./portal.db"
    # Время жизни access-токена в минутах (по умолчанию 8 часов)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Возвращает единственный экземпляр настроек (кэшируется)."""
    return Settings()
