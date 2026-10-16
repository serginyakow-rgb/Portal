"""Бизнес-логика модуля «База данных»: разделы, заготовки, теги и поиск."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.templates_db.models import Section, Tag, TemplateBlock, block_tags
from app.modules.templates_db.schemas import (
    SectionCreate,
    SectionRead,
    SectionUpdate,
    TagRead,
    TemplateBlockCreate,
    TemplateBlockListItem,
    TemplateBlockRead,
    TemplateBlockUpdate,
    preview_text,
)


class SectionNotEmptyError(Exception):
    """Нельзя удалить раздел, в котором уже есть заготовки."""


def _block_options() -> tuple:
    """Связи заготовки, которые нужно подтянуть: теги и раздел (ленивая загрузка запрещена)."""
    return (
        selectinload(TemplateBlock.tags),
        selectinload(TemplateBlock.section),
    )


def _to_list_item(block: TemplateBlock) -> TemplateBlockListItem:
    """Преобразует заготовку в карточку списка: короткий текст и имена тегов."""
    return TemplateBlockListItem(
        id=block.id,
        section_id=block.section_id,
        section_name=block.section.name if block.section else None,
        title=block.title,
        body=block.body,
        body_preview=preview_text(block.body),
        tags=[tag.name for tag in block.tags],
        author_name=block.author.full_name if block.author else None,
        updated_at=block.updated_at,
    )


def _to_block_read(block: TemplateBlock) -> TemplateBlockRead:
    """Преобразует заготовку в полное представление для просмотра и правки."""
    return TemplateBlockRead(
        id=block.id,
        section_id=block.section_id,
        section_name=block.section.name if block.section else None,
        title=block.title,
        body=block.body,
        tags=[TagRead.model_validate(tag) for tag in block.tags],
        author_name=block.author.full_name if block.author else None,
        created_at=block.created_at,
        updated_at=block.updated_at,
    )


async def _get_or_create_tags(db: AsyncSession, names: list[str]) -> list[Tag]:
    """Возвращает теги по именам, создавая отсутствующие."""
    if not names:
        return []
    result = await db.execute(select(Tag).where(Tag.name.in_(names)))
    known = {tag.name: tag for tag in result.scalars().all()}
    tags: list[Tag] = []
    for name in names:
        tag = known.get(name)
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
            known[name] = tag
        tags.append(tag)
    return tags


async def list_sections(db: AsyncSession) -> list[SectionRead]:
    """Все разделы с числом заготовок в каждом: порядок задаёт sort_order."""
    stmt = (
        select(Section, func.count(TemplateBlock.id))
        .outerjoin(TemplateBlock, TemplateBlock.section_id == Section.id)
        .group_by(Section.id)
        .order_by(Section.sort_order, Section.name)
    )
    rows = (await db.execute(stmt)).all()
    return [
        SectionRead.model_validate(section).model_copy(update={"blocks_count": count})
        for section, count in rows
    ]


async def get_section(db: AsyncSession, section_id: int) -> Section | None:
    """Раздел по идентификатору."""
    return await db.get(Section, section_id)


async def get_section_by_name(db: AsyncSession, name: str) -> Section | None:
    """Раздел по названию: названия разделов уникальны."""
    result = await db.execute(select(Section).where(Section.name == name))
    return result.scalars().first()


async def create_section(db: AsyncSession, data: SectionCreate) -> Section:
    """Создаёт раздел базы заготовок."""
    section = Section(
        name=data.name,
        description=data.description or None,
        sort_order=data.sort_order,
    )
    db.add(section)
    await db.commit()
    await db.refresh(section)
    return section


async def update_section(db: AsyncSession, section: Section, data: SectionUpdate) -> Section:
    """Меняет название, описание и порядок раздела."""
    section.name = data.name
    section.description = data.description or None
    section.sort_order = data.sort_order
    await db.commit()
    await db.refresh(section)
    return section


async def delete_section(db: AsyncSession, section: Section) -> None:
    """Удаляет раздел; непустой раздел не удаляется."""
    result = await db.execute(
        select(func.count(TemplateBlock.id)).where(TemplateBlock.section_id == section.id)
    )
    if result.scalar_one():
        raise SectionNotEmptyError("В разделе есть заготовки: сначала удалите или перенесите их")
    await db.delete(section)
    await db.commit()


async def list_blocks(
    db: AsyncSession,
    *,
    section_id: int | None = None,
    tag: str | None = None,
    query: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[TemplateBlockListItem]:
    """Заготовки с фильтрами: раздел, тег и текст (заголовок и содержание).

    Текст ищется на стороне Python: SQLite сравнивает регистр кириллицы
    некорректно (lower() в SQLite работает только с латиницей), а база
    конторы небольшая — несколько сотен заготовок, поэтому фильтрация
    в памяти незаметна по скорости.
    """
    stmt = (
        select(TemplateBlock)
        .options(*_block_options())
        .join(Section, Section.id == TemplateBlock.section_id)
        .order_by(Section.sort_order, Section.name, TemplateBlock.title)
    )
    if section_id:
        stmt = stmt.where(TemplateBlock.section_id == section_id)
    if tag:
        stmt = (
            stmt.join(block_tags, block_tags.c.block_id == TemplateBlock.id)
            .join(Tag, Tag.id == block_tags.c.tag_id)
            .where(Tag.name == tag.strip().lower())
        )
    result = await db.execute(stmt)
    blocks = list(result.scalars().unique().all())
    if query:
        needle = query.strip().casefold()
        blocks = [
            block
            for block in blocks
            if needle in block.title.casefold() or needle in block.body.casefold()
        ]
    if offset:
        blocks = blocks[offset:]
    if limit:
        blocks = blocks[:limit]
    return [_to_list_item(block) for block in blocks]


async def get_block(db: AsyncSession, block_id: int) -> TemplateBlock | None:
    """Заготовка по идентификатору вместе с тегами, разделом и автором."""
    result = await db.execute(
        select(TemplateBlock).options(*_block_options()).where(TemplateBlock.id == block_id)
    )
    return result.scalars().unique().one_or_none()


async def read_block(db: AsyncSession, block_id: int) -> TemplateBlockRead | None:
    """Представление заготовки для страницы просмотра и формы правки."""
    block = await get_block(db, block_id)
    return _to_block_read(block) if block is not None else None


async def create_block(
    db: AsyncSession,
    data: TemplateBlockCreate,
    *,
    created_by: int | None = None,
) -> TemplateBlock:
    """Создаёт заготовку, автоматически добавляя новые теги."""
    block = TemplateBlock(
        section_id=data.section_id,
        title=data.title,
        body=data.body,
        created_by=created_by,
    )
    block.tags = await _get_or_create_tags(db, data.tags)
    db.add(block)
    await db.commit()
    # Перечитываем заготовку: связи нужны сразу после создания
    created = await get_block(db, block.id)
    return created if created is not None else block


async def update_block(
    db: AsyncSession,
    block: TemplateBlock,
    data: TemplateBlockUpdate,
) -> TemplateBlock:
    """Меняет поля заготовки и пересобирает набор её тегов."""
    block.section_id = data.section_id
    block.title = data.title
    block.body = data.body
    block.tags = await _get_or_create_tags(db, data.tags)
    await db.commit()
    updated = await get_block(db, block.id)
    return updated if updated is not None else block


async def delete_block(db: AsyncSession, block: TemplateBlock) -> None:
    """Удаляет заготовку вместе с её связями с тегами."""
    await db.delete(block)
    await db.commit()
