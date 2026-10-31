"""Точка входа: сборка FastAPI, статика, шаблоны, метка меню и обработчики ошибок."""
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import async_session_maker, engine
from app.core.templating import MENU_PANEL, render
from app.db.base import Base

# Модели импортируются до create_all, иначе SQLAlchemy не знает о таблицах
from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.auth.dependencies import CurrentUser, get_optional_user
from app.modules.auth.routes import router as auth_router
from app.modules.calculators.routes import router as calculators_router
from app.modules.settings.routes import router as settings_router
from app.modules.tasks import models as tasks_models  # noqa: F401 (таблица tasks)
from app.modules.tasks.routes import router as tasks_router
from app.modules.tasks.service import count_menu_badge
from app.modules.templates_db.routes import router as templates_db_router


logger = logging.getLogger(__name__)


async def _enable_sqlite_wal() -> None:
    """Переводит SQLite-базу в режим WAL; для других СУБД ничего не делает.

    Синхронизация разделов добавляет постоянные чтения (экраны сотрудников
    опрашивают сервер каждые несколько секунд), а в журнале по умолчанию
    чтения ждут каждую запись. WAL позволяет читать во время записи; прагма
    хранится в самом файле базы, поэтому её достаточно выставить при старте.
    Внутри транзакции журнал не переключается — запрос идёт в режиме
    AUTOCOMMIT. Сбой (например, файл открыт только на чтение) запуску
    не мешает: остаётся прежний журнал, портал работает как раньше.
    """
    async with engine.connect() as conn:
        if conn.dialect.name != "sqlite":
            return
        autocommit = await conn.execution_options(isolation_level="AUTOCOMMIT")
        try:
            await autocommit.exec_driver_sql("PRAGMA journal_mode=WAL")
        except SQLAlchemyError as exc:
            logger.warning("Режим WAL для SQLite не включён: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Создаёт таблицы БД при старте и освобождает движок при остановке."""
    await _enable_sqlite_wal()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


class NoCacheStaticFiles(StaticFiles):
    """Статика с обязательной перепроверкой у сервера.

    Без заголовка Cache-Control браузер держит styles.css и app.js в
    эвристическом кеше и продолжает показывать старую вёрстку — правки
    интерфейса не доходили до сотрудников даже после обновления страницы.
    """

    async def get_response(self, path: str, scope: Any) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app = FastAPI(title="Портал нотариальной конторы", lifespan=lifespan)

app.mount("/static", NoCacheStaticFiles(directory="app/static"), name="static")
app.state.templates = Jinja2Templates(directory="app/templates")


@app.middleware("http")
async def tasks_menu_badge(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Считает метку «Задачи» в левом меню один раз на страницу.

    Меню общее для всех страниц, поэтому числа нужны не только в разделе
    «Задачи». Значение кладётся в request.state, откуда его забирает render()
    (core/templating.py); по умолчанию — None, метки нет: так страница входа
    и статика остаются без лишних запросов к БД. Сессия закрывается до
    call_next, чтобы не держать два соединения к SQLite одновременно.
    """
    request.state.tasks_badge = None
    if request.method == "GET" and not request.url.path.startswith("/static"):
        async with async_session_maker() as db:
            user = await get_optional_user(request, db)
            if user is not None:
                request.state.tasks_badge = await count_menu_badge(db, user.id)
    return await call_next(request)


app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(calculators_router, prefix="/calculators", tags=["calculators"])
app.include_router(tasks_router, prefix="/tasks")
app.include_router(templates_db_router, prefix="/templates-db")


@app.get("/")
async def root() -> RedirectResponse:
    """Корень портала: ведём на панель, неавторизованных встретит обработчик 401."""
    return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: CurrentUser, denied: bool = False) -> HTMLResponse:
    """Главная зона портала: демонстрационных карточек нет, реальные дела появятся в следующих задачах."""
    return render(
        request,
        "dashboard/index.html",
        user=user,
        active_menu=MENU_PANEL,
        denied=denied,
    )


@app.exception_handler(status.HTTP_401_UNAUTHORIZED)
async def unauthorized_handler(request: Request, exc: HTTPException) -> RedirectResponse:
    """Неавторизованного сотрудника отправляем на страницу входа."""
    return RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)


@app.exception_handler(status.HTTP_403_FORBIDDEN)
async def forbidden_handler(request: Request, exc: HTTPException) -> RedirectResponse:
    """Сотрудника без нужных прав возвращаем на панель с пояснением."""
    return RedirectResponse("/dashboard?denied=1", status_code=status.HTTP_303_SEE_OTHER)
