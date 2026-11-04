"""Схемы (Pydantic) модуля «Настройки»: тарифы и шаблоны карточек «Задач»."""
from typing import Any

from pydantic import BaseModel, field_validator

# Границы поля «Вид имущества»
MAX_ASSET_TYPE = 200

# Шаблон карточки раздела «Задачи»: длина названия и число пунктов проверки
MAX_TEMPLATE_TITLE = 200
MAX_TEMPLATE_CHECKS = 10


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


class CardTemplateInput(BaseModel):
    """Данные окна «Добавить шаблон»: название и описания отмеченных пунктов.

    Пункты приходят уже отобранными: маршрут берёт описание только из тех
    строк формы, где стоит чек-бокс, поэтому неотмеченные поля сюда
    не попадают. Пустой список разрешён — шаблон может быть без пунктов.
    """

    title: str = ""
    checks: list[str] = []

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        """Схлопывает пробелы и требует непустое название шаблона."""
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Название шаблона обязательно")
        if len(cleaned) > MAX_TEMPLATE_TITLE:
            raise ValueError(
                f"Название шаблона слишком длинное (максимум {MAX_TEMPLATE_TITLE} символов)"
            )
        return cleaned

    @field_validator("checks")
    @classmethod
    def validate_checks(cls, value: list[str]) -> list[str]:
        """Схлопывает пробелы, выбрасывает пустые описания и держит предел в 10."""
        cleaned = [" ".join(item.split()) for item in value]
        cleaned = [item for item in cleaned if item]
        if len(cleaned) > MAX_TEMPLATE_CHECKS:
            raise ValueError(
                f"Пунктов проверки слишком много (максимум {MAX_TEMPLATE_CHECKS})"
            )
        return cleaned
