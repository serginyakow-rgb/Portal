"""Подключение к БД: асинхронный движок, фабрика сессий и зависимость get_db()."""
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_IS_SQLITE = get_settings().DATABASE_URL.startswith("sqlite")

# Таймаут ожидания блокировки SQLite, секунды. Синхронизация разделов добавляет
# постоянные чтения параллельно записям (экраны сотрудников опрашивают сервер),
# и запросу лучше подождать чужой коммит, чем упасть с «database is locked».
# Для PostgreSQL (позже) параметр не нужен и не передаётся
_CONNECT_ARGS: dict[str, int] = {"timeout": 15} if _IS_SQLITE else {}

# Асинхронный движок (разрешённая глобальная переменная)
engine = create_async_engine(
    get_settings().DATABASE_URL,
    echo=False,
    future=True,
    connect_args=_CONNECT_ARGS,
)

if _IS_SQLITE:

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_synchronous(dbapi_connection: Any, connection_record: Any) -> None:
        """Ставит synchronous=NORMAL на каждое соединение SQLite.

        Умолчание SQLite — FULL: каждый commit ждёт fsync журнала, а опрос
        экранов и сохранение карточек пишут в базу часто, поэтому сотрудник
        ждал диск на каждой правке. При журнале WAL (включается при старте,
        app.main._enable_sqlite_wal) NORMAL безопасен: база не повреждается
        при отключении питания, незавершённой остаётся максимум последняя
        транзакция. Прагма действует на соединение, а не на файл базы, поэтому
        её ставят здесь — на connect, для каждого соединения пула.
        """
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()


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
