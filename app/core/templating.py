"""Рендеринг Jinja2-шаблонов: единый контекст для всех страниц портала."""
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.modules.auth.models import User

# Человекочитаемые названия ролей портала
ROLE_LABELS = {"admin": "Нотариус", "user": "Сотрудник"}

# Значения active_menu для подсветки активного пункта левого меню
MENU_PANEL = "panel"
MENU_PROFILE = "profile"


def initials(full_name: str) -> str:
    """Инициалы из имени (ФИО) для аватара в шапке."""
    parts = [part for part in full_name.split() if part]
    return "".join(part[0].upper() for part in parts[:2]) or "?"


def render_partial(request: Request, template_name: str, **context: Any) -> HTMLResponse:
    """Рендерит фрагмент страницы — без шапки, меню и общего контекста.

    Фрагменты запрашивает JavaScript: например, кнопка «Загрузить ещё…»
    в «Базе данных» получает следующую порцию карточек и дописывает её
    в сетку (маршрут ``GET /templates-db/blocks/more``). Шаблону фрагмента
    нужен только тот контекст, который передали явно.
    """
    return request.app.state.templates.TemplateResponse(request, template_name, context)


def render(
    request: Request,
    template_name: str,
    *,
    user: User | None = None,
    active_menu: str | None = None,
    status_code: int = 200,
    **context: Any,
) -> HTMLResponse:
    """Рендерит шаблон, добавляя общий для всех страниц контекст.

    ``tasks_badge`` кладёт middleware в ``request.state`` (app/main.py): это
    числа метки «Задачи» в левом меню — ничьи карточки, карточки сотрудника
    в работе и его срочные карточки; None — если пользователь не вошёл
    или middleware не выполнялась.
    """
    page_context: dict[str, Any] = {
        "user": user,
        "initials": initials(user.full_name) if user is not None else "?",
        "role_label": ROLE_LABELS.get(user.role, user.role) if user is not None else "",
        "role_labels": ROLE_LABELS,
        "active_menu": active_menu,
        "tasks_badge": getattr(request.state, "tasks_badge", None),
    }
    page_context.update(context)
    return request.app.state.templates.TemplateResponse(
        request,
        template_name,
        page_context,
        status_code=status_code,
    )
