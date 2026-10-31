"""Подключение к БД: асинхронный движок, фабрика сессий и зависимость get_db()."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

# Таймаут ожидания блокировки SQLite, секунды. Синхронизация разделов добавляет
# постоянные чтения параллельно записям (экраны сотрудников опрашивают сервер),
# и запросу лучше подождать чужой коммит, чем упасть с «database is locked».
# Для PostgreSQL (позже) параметр не нужен и не передаётся
_CONNECT_ARGS: dict[str, int] = (
    {"timeout": 15} if get_settings().DATABASE_URL.startswith("sqlite") else {}
)

# Асинхронный движок (разрешённая глобальная переменная)
engine = create_async_engine(
    get_settings().DATABASE_URL,
    echo=False,
    future=True,
    connect_args=_CONNECT_ARGS,
)

# Фабрика асинхронных сессий (разрешённая глобальная переменная)
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Зависимость FastAPI: открывает сессию на время запроса и закрывает её."""
    async with async_session_maker() as session:
        yield session
