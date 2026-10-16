"""Бизнес-логика модуля «Калькуляторы»: расчёт госпошлины за нотариальные действия.

Калькуляторы stateless: ничего не сохраняют в базу, моделей БД у модуля нет.
Добавление нового калькулятора — новая функция расчёта здесь, новый шаблон
и новый роут: существующий код переписывать не нужно.

Тариф за удостоверение договора купли-продажи недвижимости считается в браузере
(app/static/js/calculators.js): так показатели обновляются сразу при вводе,
а значения полей переживают перезагрузку страницы в localStorage.
"""
from dataclasses import dataclass

from app.modules.calculators.schemas import (
    DEAL_TYPE_LABELS,
    PAYER_TYPE_LABELS,
    DealType,
    GosposhlinaResult,
    PayerType,
)


@dataclass(frozen=True)
class CalculatorCard:
    """Карточка калькулятора на главной странице раздела."""

    title: str
    description: str
    url: str


# Каталог раздела: чтобы добавить калькулятор, допишите карточку и роут
CALCULATORS: tuple[CalculatorCard, ...] = (
    CalculatorCard(
        title="Удостоверение договора купли-продажи недвижимости",
        description="Обязательная нотариальная форма",
        url="/calculators/kuplya-prodazha",
    ),
)


def list_calculators() -> list[CalculatorCard]:
    """Список доступных калькуляторов раздела."""
    return list(CALCULATORS)


def format_money(value: float) -> str:
    """Сумма в виде «1 500 000,00»: пробел — тысячи, запятая — копейки."""
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def _format_percent(rate: float) -> str:
    """Ставка в виде «0,3 %» без лишних нулей."""
    return f"{rate * 100:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " %"


@dataclass(frozen=True)
class Tariff:
    """Нотариальный тариф: доля от суммы договора либо фиксированная сумма."""

    rate: float = 0.0
    minimum: float = 0.0
    fixed: float | None = None


# Тарифы за удостоверение сделок: общеизвестные ставки (ст. 22 Основ
# законодательства РФ о нотариате, ст. 333.24 НК РФ).
# Точные ставки, льготы и УПТХ — УТОЧНИТЬ У НОТАРИУСА.
TARIFFS: dict[tuple[DealType, PayerType], Tariff] = {
    ("realty", "close"): Tariff(rate=0.003, minimum=300.0),
    ("realty", "other"): Tariff(rate=0.01, minimum=1000.0),
    ("transport", "close"): Tariff(rate=0.003, minimum=300.0),
    ("transport", "other"): Tariff(rate=0.01, minimum=1000.0),
    ("marriage", "close"): Tariff(fixed=500.0),
    ("marriage", "other"): Tariff(fixed=500.0),
}


def calculate_gosposhlina(
    amount: float,
    deal_type: DealType = "realty",
    payer_type: PayerType = "other",
) -> GosposhlinaResult:
    """Считает госпошлину за удостоверение сделки: чистая функция без БД и сессии."""
    tariff = TARIFFS[(deal_type, payer_type)]
    if tariff.fixed is not None:
        return GosposhlinaResult(
            result=round(tariff.fixed, 2),
            detail=(
                f"{DEAL_TYPE_LABELS[deal_type]}: фиксированный тариф "
                f"{format_money(tariff.fixed)} ₽ от суммы договора не зависит"
            ),
        )

    by_rate = round(amount * tariff.rate, 2)
    if by_rate < tariff.minimum:
        note = f"применён минимальный тариф {format_money(tariff.minimum)} ₽"
    else:
        note = f"минимум {format_money(tariff.minimum)} ₽ не применён"
    detail = (
        f"{_format_percent(tariff.rate)} от {format_money(amount)} ₽ = "
        f"{format_money(by_rate)} ₽; {note}. "
        f"Плательщик: {PAYER_TYPE_LABELS[payer_type].lower()}."
    )
    return GosposhlinaResult(result=round(max(by_rate, tariff.minimum), 2), detail=detail)
