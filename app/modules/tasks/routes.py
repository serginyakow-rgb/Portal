"""Маршруты модуля «Задачи»: страница раздела.

Префикс адресов (/tasks) задаётся при подключении роутера в app/main.py,
поэтому внутри модуля путь указан без префикса.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.templating import render
from app.modules.auth.dependencies import CurrentUser

router = APIRouter(tags=["tasks"])

# Значение active_menu для подсветки пункта «Задачи» в левом меню
MENU_TASKS = "tasks"


@router.get("/", response_class=HTMLResponse, response_model=None)
async def index_page(request: Request, user: CurrentUser) -> HTMLResponse:
    """Страница раздела «Задачи»: список задач появится в следующих задачах."""
    return render(
        request,
        "tasks/index.html",
        user=user,
        active_menu=MENU_TASKS,
    )
