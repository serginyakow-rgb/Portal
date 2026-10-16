"""Модели модуля «База данных»: разделы заготовок, заготовки и теги.

Модуль самодостаточен: модель User из модуля auth не импортируется. Внешний
ключ автора задан строкой «users.id», а связь author разрешается по имени
класса User, который уже зарегистрирован в общем Base из app.db.base.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Ассоциативная таблица «заготовка — тег» (многие ко многим)
block_tags = Table(
    "block_tags",
    Base.metadata,
    Column("block_id", ForeignKey("template_blocks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Section(Base):
    """Раздел базы заготовок: «Договоры», «Доверенности», «Согласия»."""

    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    blocks: Mapped[list["TemplateBlock"]] = relationship(back_populates="section")

    def __repr__(self) -> str:  # pragma: no cover - отладочное представление
        return f"<Section id={self.id} name={self.name!r}>"


class Tag(Base):
    """Свободная метка заготовки; хранится в нижнем регистре."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)

    blocks: Mapped[list["TemplateBlock"]] = relationship(
        secondary=block_tags,
        back_populates="tags",
    )

    def __repr__(self) -> str:  # pragma: no cover - отладочное представление
        return f"<Tag id={self.id} name={self.name!r}>"


class TemplateBlock(Base):
    """Текстовая заготовка: заголовок, многострочное тело, теги и автор."""

    __tablename__ = "template_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("sections.id"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Автор хранится ссылкой на users.id: модуль auth не импортируется
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    section: Mapped["Section"] = relationship(back_populates="blocks")
    tags: Mapped[list["Tag"]] = relationship(
        secondary=block_tags,
        back_populates="blocks",
        order_by="Tag.name",
    )
    # Автор читается вместе с заготовкой: в async-сессии ленивая загрузка запрещена
    author = relationship("User", lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover - отладочное представление
        return f"<TemplateBlock id={self.id} title={self.title!r}>"
