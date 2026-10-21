"""Схемы (Pydantic) модуля «Настройки»: справочник региональных тарифов."""
from typing import Any

from pydantic import BaseModel, field_validator

# Границы поля «Вид имущества»
MAX_ASSET_TYPE = 200


class InheritanceTariffInput(BaseModel):
    """Данные формы строки справочника: вид имущества и региональный тариф."""

    asset_type: str = ""
    rate: int

    @field_validator("asset_type")
    @classmethod
    def validate_asset_type(cls, value: str) -> str:
        """Схлопывает пробелы и требует непустой вид имущества."""
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Вид имущества обязателен")
        if len(cleaned) > MAX_ASSET_TYPE:
            raise ValueError(f"Вид имущества слишком длинный (максимум {MAX_ASSET_TYPE} символов)")
        return cleaned

    @field_validator("rate", mode="before")
    @classmethod
    def prepare_rate(cls, value: Any) -> Any:
        """Принимает число из формы: убирает пробелы, пустое значение — ошибка."""
        if isinstance(value, str):
            cleaned = value.replace("\u00a0", " ").replace(" ", "").strip()
            if not cleaned:
                raise ValueError("Региональный тариф обязателен")
            try:
                return int(cleaned)
            except ValueError as exc:
                raise ValueError("Региональный тариф должен быть целым числом") from exc
        return value

    @field_validator("rate")
    @classmethod
    def validate_rate(cls, value: int) -> int:
        """Тариф — целое число больше нуля."""
        if value <= 0:
            raise ValueError("Региональный тариф должен быть больше 0")
        return value
