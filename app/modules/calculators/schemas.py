"""Схемы (Pydantic) модуля «Калькуляторы»: проверка полей формы расчёта."""
from typing import Any, Literal

from pydantic import BaseModel, field_validator

# Верхняя граница суммы договора: защита от случайно вставленного мусора
MAX_AMOUNT = 1_000_000_000.0

# Тип сделки и категория плательщика: значения совпадают с ключами тарифов
# в service.py, поэтому новую сделку нужно добавить и здесь, и в TARIFFS
DealType = Literal["realty", "transport", "marriage"]
PayerType = Literal["close", "other"]

# Подписи для выпадающих списков формы: порядок словаря = порядок в списке
DEAL_TYPE_LABELS: dict[DealType, str] = {
    "realty": "Договор отчуждения недвижимости",
    "transport": "Договор отчуждения транспортного средства",
    "marriage": "Брачный договор",
}

PAYER_TYPE_LABELS: dict[PayerType, str] = {
    "close": "Супруг, родители, дети, внуки",
    "other": "Иные лица",
}

# Подписи выпадающего списка калькулятора удостоверения ДКП (необязательная
# нотариальная форма): кому отчуждается недвижимость. Ключи — те же категории,
# что и у плательщика, и совпадают с ключами правил расчёта в
# app/static/js/udostoverenie-dkp.js. Порядок словаря = порядок в списке.
DKP_RECIPIENT_LABELS: dict[PayerType, str] = {
    "close": "Супругу, родителям, детям, внукам",
    "other": "Другим лицам",
}

# Подписи выпадающего списка калькулятора удостоверения договора дарения
# недвижимости: кому дарится недвижимость. Ключи — те же категории, что и у
# плательщика, и совпадают с ключами правил расчёта в
# app/static/js/udostoverenie-dareniya.js. Порядок словаря = порядок в списке.
DARENIE_RECIPIENT_LABELS: dict[PayerType, str] = {
    "close": "Родственникам",
    "other": "Другим лицам",
}

DEFAULT_DEAL_TYPE: DealType = "realty"
DEFAULT_PAYER_TYPE: PayerType = "other"


class GosposhlinaInput(BaseModel):
    """Данные формы калькулятора госпошлины."""

    amount: float = 0.0
    deal_type: DealType = DEFAULT_DEAL_TYPE
    payer_type: PayerType = DEFAULT_PAYER_TYPE

    @field_validator("amount", mode="before")
    @classmethod
    def prepare_amount(cls, value: Any) -> Any:
        """Принимает «1 500 000,50» из формы: убирает пробелы, запятую меняет на точку."""
        if value is None:
            return 0.0
        if isinstance(value, str):
            cleaned = value.replace("\u00a0", " ").replace(" ", "").replace(",", ".").strip()
            if not cleaned:
                return 0.0
            try:
                return float(cleaned)
            except ValueError as exc:
                raise ValueError("Сумма договора должна быть числом") from exc
        return value

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Сумма договора должна быть больше нуля")
        if value > MAX_AMOUNT:
            limit = f"{MAX_AMOUNT:,.0f}".replace(",", " ")
            raise ValueError(f"Сумма договора слишком большая (максимум {limit} ₽)")
        return round(value, 2)

    @field_validator("deal_type", mode="before")
    @classmethod
    def validate_deal_type(cls, value: Any) -> Any:
        """Значение приходит из select: постороннее значение отклоняем."""
        if value not in DEAL_TYPE_LABELS:
            raise ValueError("Выберите тип сделки из списка")
        return value

    @field_validator("payer_type", mode="before")
    @classmethod
    def validate_payer_type(cls, value: Any) -> Any:
        """Значение приходит из select: постороннее значение отклоняем."""
        if value not in PAYER_TYPE_LABELS:
            raise ValueError("Выберите категорию плательщика из списка")
        return value


class GosposhlinaResult(BaseModel):
    """Итог расчёта: сумма госпошлины и пояснение, из чего она получилась."""

    result: float
    detail: str
