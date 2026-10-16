"""Маршруты модуля «Калькуляторы»: список калькуляторов, тариф за удостоверение
договора купли-продажи недвижимости и расчёт госпошлины.

Префикс адресов (/calculators) задаётся при подключении роутера в app/main.py,
поэтому внутри модуля пути указаны без префикса.
"""
from typing import Annotated

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from app.core.templating import render
from app.modules.auth.dependencies import CurrentUser
from app.modules.auth.models import User
from app.modules.calculators.schemas import (
    DEFAULT_DEAL_TYPE,
    DEFAULT_PAYER_TYPE,
    DEAL_TYPE_LABELS,
    PAYER_TYPE_LABELS,
    GosposhlinaInput,
    GosposhlinaResult,
)
from app.modules.calculators.service import (
    calculate_gosposhlina,
    format_money,
    list_calculators,
)

router = APIRouter(tags=["calculators"])

# Значение active_menu для подсветки пункта «Калькуляторы» в левом меню
MENU_CALCULATORS = "calculators"


def _validation_message(exc: ValidationError) -> str:
    """Возвращает первое сообщение об ошибке валидации в читаемом виде."""
    message = str(exc.errors()[0].get("msg", "Некорректные данные"))
    return message.removeprefix("Value error, ")


def _render_gosposhlina(
    request: Request,
    user: User,
    *,
    amount: str = "",
    deal_type: str = DEFAULT_DEAL_TYPE,
    payer_type: str = DEFAULT_PAYER_TYPE,
    result: GosposhlinaResult | None = None,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит страницу калькулятора: слева форма, справа результат расчёта."""
    return render(
        request,
        "calculators/gosposhlina.html",
        user=user,
        active_menu=MENU_CALCULATORS,
        amount=amount,
        deal_type=deal_type,
        payer_type=payer_type,
        deal_types=DEAL_TYPE_LABELS,
        payer_types=PAYER_TYPE_LABELS,
        result=result,
        result_text=format_money(result.result) if result is not None else "",
        error=error,
        status_code=status_code,
    )


@router.get("/", response_class=HTMLResponse, response_model=None)
async def index_page(request: Request, user: CurrentUser) -> HTMLResponse:
    """Главная страница раздела: карточки доступных калькуляторов."""
    return render(
        request,
        "calculators/index.html",
        user=user,
        active_menu=MENU_CALCULATORS,
        calculators=list_calculators(),
    )


@router.get("/kuplya-prodazha", response_class=HTMLResponse, response_model=None)
async def kuplya_prodazha_page(request: Request, user: CurrentUser) -> HTMLResponse:
    """Калькулятор тарифа за удостоверение договора купли-продажи недвижимости.

    Расчёт выполняет браузер (static/js/calculators.js): показатели обновляются
    сразу при вводе, а значения полей сохраняются в localStorage.
    """
    return render(
        request,
        "calculators/kuplya_prodazha.html",
        user=user,
        active_menu=MENU_CALCULATORS,
    )


@router.get("/gosposhlina", response_class=HTMLResponse, response_model=None)
async def gosposhlina_page(request: Request, user: CurrentUser) -> HTMLResponse:
    """Форма калькулятора госпошлины: расчёта ещё нет."""
    return _render_gosposhlina(request, user)


@router.post("/gosposhlina", response_class=HTMLResponse, response_model=None)
async def gosposhlina_calculate(
    request: Request,
    user: CurrentUser,
    amount: Annotated[str, Form()] = "",
    deal_type: Annotated[str, Form()] = DEFAULT_DEAL_TYPE,
    payer_type: Annotated[str, Form()] = DEFAULT_PAYER_TYPE,
) -> HTMLResponse:
    """Проверяет поля формы и возвращает результат расчёта на той же странице."""
    try:
        data = GosposhlinaInput(
            amount=amount,
            deal_type=deal_type,
            payer_type=payer_type,
        )
    except ValidationError as exc:
        return _render_gosposhlina(
            request,
            user,
            amount=amount,
            deal_type=deal_type,
            payer_type=payer_type,
            error=_validation_message(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return _render_gosposhlina(
        request,
        user,
        amount=amount,
        deal_type=data.deal_type,
        payer_type=data.payer_type,
        result=calculate_gosposhlina(data.amount, data.deal_type, data.payer_type),
    )
