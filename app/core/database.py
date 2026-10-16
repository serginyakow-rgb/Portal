"""Подключение к БД: асинхронный движок, фабрика сессий и зависимость get_db()."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

# Асинхронный движок (разрешённая глобальная переменная)
engine = create_async_engine(get_settings().DATABASE_URL, echo=False, future=True)

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
