"""Точка входа: сборка FastAPI, статика, шаблоны и обработчики ошибок."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.database import engine
from app.core.templating import MENU_PANEL, render
from app.db.base import Base

# Модели импортируются до create_all, иначе SQLAlchemy не знает о таблицах
from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.auth.dependencies import CurrentUser
from app.modules.auth.routes import router as auth_router
from app.modules.calculators.routes import router as calculators_router
from app.modules.settings.routes import router as settings_router
from app.modules.tasks import models as tasks_models  # noqa: F401 (таблица tasks)
from app.modules.tasks.routes import router as tasks_router
from app.modules.templates_db.routes import router as templates_db_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Создаёт таблицы БД при старте и освобождает движок при остановке."""
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
