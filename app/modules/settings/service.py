"""Бизнес-логика модуля «Настройки»: тарифы и шаблоны карточек раздела «Задачи».

Функция ``list_inheritance_tariffs`` — точка доступа к справочнику для других
модулей портала (например, для выпадающего списка в калькуляторах).
Шаблоны карточек (``list_card_templates``, ``get_card_template``,
``create_card_template``, ``update_card_template``, ``delete_card_template``)
читает и меняет раздел настроек «Шаблоны карточек для раздела «Задачи»».
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.settings.models import CardTemplate, InheritanceTariff
from app.modules.settings.schemas import CardTemplateInput, InheritanceTariffInput


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


async def list_card_templates(db: AsyncSession) -> list[CardTemplate]:
    """Все шаблоны карточек раздела «Задачи» в алфавитном порядке названий."""
    result = await db.execute(
        # Как у списков сотрудников и контактов: название, затем id — при
        # одинаковых названиях порядок остаётся устойчивым
        select(CardTemplate).order_by(CardTemplate.title, CardTemplate.id)
    )
    return list(result.scalars().all())


async def get_card_template(db: AsyncSession, template_id: int) -> CardTemplate | None:
    """Шаблон карточки по идентификатору."""
    return await db.get(CardTemplate, template_id)


async def create_card_template(db: AsyncSession, data: CardTemplateInput) -> CardTemplate:
    """Добавляет шаблон карточки: название и пункты проверки по порядку."""
    template = CardTemplate(title=data.title, checks=list(data.checks))
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def update_card_template(
    db: AsyncSession,
    template: CardTemplate,
    data: CardTemplateInput,
) -> CardTemplate:
    """Меняет название шаблона и пункты проверки (порядок пунктов сохраняется)."""
    template.title = data.title
    template.checks = list(data.checks)
    await db.commit()
    await db.refresh(template)
    return template


async def delete_card_template(db: AsyncSession, template: CardTemplate) -> None:
    """Удаляет шаблон карточки без возможности восстановления."""
    await db.delete(template)
    await db.commit()
