"""Бизнес-логика модуля «Калькуляторы»: расчёт госпошлины за нотариальные действия.

Калькуляторы stateless: ничего не сохраняют в базу, моделей БД у модуля нет.
Добавление нового калькулятора — новая функция расчёта здесь, новый шаблон
и новый роут: существующий код переписывать не нужно.

Тариф за удостоверение договора купли-продажи недвижимости и нотариальный тариф
за удостоверение ДКП (необязательная форма) считаются в браузере
(app/static/js/calculators.js и app/static/js/udostoverenie-dkp.js): так
показатели обновляются сразу при вводе, а значения полей переживают
перезагрузку страницы в localStorage.
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


# Каталог раздела, разбитый на блоки: на странице каждый блок — отдельная
# панель, блоки разделены горизонтальными линиями, названий у блоков нет.
# Пустой url — калькулятор ещё не готов: кнопка «Открыть» выводится заглушкой.
# Чтобы добавить калькулятор, допишите карточку в нужный блок и роут.
CALCULATOR_BLOCKS: tuple[tuple[CalculatorCard, ...], ...] = (
    # Блок 1: расчёты и сдача
    (
        CalculatorCard(
            title="Расчет и сдача",
            description="",
            url="/calculators/raschet-i-sdacha",
        ),
        CalculatorCard(
            title="Удостоверение копий и равнозначность документов",
            description="",
            url="/calculators/udostoverenie-kopiy",
        ),
    ),
    # Блок 2: готовые калькуляторы раздела
    (
        CalculatorCard(
            title="Удостоверение договора купли-продажи недвижимости",
            description="Обязательная нотариальная форма",
            url="/calculators/kuplya-prodazha",
        ),
        CalculatorCard(
            title="Удостоверение договора купли-продажи недвижимости",
            description="Необязательная нотариальная форма",
            url="/calculators/udostoverenie-dkp",
        ),
        CalculatorCard(
            title="Удостоверение договора дарения недвижимости",
            # Пустое описание — карточка выводится без строки .card__meta
            description="",
            url="/calculators/udostoverenie-dareniya",
        ),
        CalculatorCard(
            title="Удостоверение соглашения о выделении долей по МСК",
            description="Соглашение о выделении долей детям",
            url="/calculators/vydelenie-doley-msk",
        ),
    ),
    # Блок 3: свидетельства о праве на наследство
    (
        CalculatorCard(
            title="Свидетельство о праве на наследство на недвижимое имущество",
            description="",
            url="/calculators/nasledstvo-nedvizhimost",
        ),
        CalculatorCard(
            title="Свидетельство о праве на наследство на автотранспорт",
            description="",
            url="",
        ),
        CalculatorCard(
            title="Свидетельство о праве на наследство на акции",
            description="",
            url="",
        ),
    ),
)

# Плоский список всех карточек в порядке вывода на странице
CALCULATORS: tuple[CalculatorCard, ...] = tuple(
    calculator for block in CALCULATOR_BLOCKS for calculator in block
)


def list_calculator_blocks() -> list[tuple[CalculatorCard, ...]]:
    """Блоки карточек раздела в порядке вывода."""
    return list(CALCULATOR_BLOCKS)


def list_calculators() -> list[CalculatorCard]:
    """Все калькуляторы раздела по порядку (включая ещё не готовые)."""
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
