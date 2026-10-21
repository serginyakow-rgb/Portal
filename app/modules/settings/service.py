"""Бизнес-логика модуля «Настройки»: справочник региональных тарифов для наследства.

Функция ``list_inheritance_tariffs`` — точка доступа к справочнику для других
модулей портала (например, для выпадающего списка в калькуляторах).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.settings.models import InheritanceTariff
from app.modules.settings.schemas import InheritanceTariffInput


async def list_inheritance_tariffs(db: AsyncSession) -> list[InheritanceTariff]:
    """Все строки справочника в алфавитном порядке видов имущества."""
    result = await db.execute(select(InheritanceTariff).order_by(InheritanceTariff.asset_type))
    return list(result.scalars().all())


async def get_inheritance_tariff(db: AsyncSession, tariff_id: int) -> InheritanceTariff | None:
    """Строка справочника по идентификатору."""
    return await db.get(InheritanceTariff, tariff_id)


async def create_inheritance_tariff(
    db: AsyncSession,
    data: InheritanceTariffInput,
) -> InheritanceTariff:
    """Добавляет строку справочника."""
    tariff = InheritanceTariff(asset_type=data.asset_type, rate=data.rate)
    db.add(tariff)
    await db.commit()
    await db.refresh(tariff)
    return tariff


async def update_inheritance_tariff(
    db: AsyncSession,
    tariff: InheritanceTariff,
    data: InheritanceTariffInput,
) -> InheritanceTariff:
    """Меняет вид имущества и региональный тариф строки."""
    tariff.asset_type = data.asset_type
    tariff.rate = data.rate
    await db.commit()
    await db.refresh(tariff)
    return tariff


async def delete_inheritance_tariff(db: AsyncSession, tariff: InheritanceTariff) -> None:
    """Удаляет строку справочника."""
    await db.delete(tariff)
    await db.commit()
