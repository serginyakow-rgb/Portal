"""Схемы (Pydantic) модуля «База данных»: разделы, заготовки и теги."""
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

# Границы длины полей
MAX_SECTION_NAME = 120
MAX_SECTION_DESCRIPTION = 500
MAX_TITLE = 200
MAX_TAGS = 15
MAX_TAG = 40
# Сколько символов тела показываем в карточке списка
PREVIEW_LENGTH = 180

# Тег: буквы (русские и латинские), цифры, пробел, дефис и подчёркивание
TAG_PATTERN = re.compile(r"^[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9 _-]*$")


def normalize_tags(raw: Any) -> list[str]:
    """Приводит теги к единому виду: нижний регистр, без пустых меток и повторов."""
    if raw is None:
        return []
    chunks = raw.replace(";", ",").split(",") if isinstance(raw, str) else list(raw)
    tags: list[str] = []
    for chunk in chunks:
        tag = " ".join(str(chunk).split()).lower()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def preview_text(body: str) -> str:
    """Короткий фрагмент тела заготовки для карточки списка."""
    flat = " ".join(body.split())
    if len(flat) <= PREVIEW_LENGTH:
        return flat
    return flat[:PREVIEW_LENGTH].rstrip() + "…"


class _TagsForm(BaseModel):
    """Общая проверка тегов: список меток в нижнем регистре без дублей."""

    tags: list[str] = []

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, value: Any) -> list[str]:
        """Принимает строку «метка, метка» из формы и приводит её к списку."""
        tags = normalize_tags(value)
        if len(tags) > MAX_TAGS:
            raise ValueError(f"У одной заготовки может быть не более {MAX_TAGS} тегов")
        for tag in tags:
            if len(tag) > MAX_TAG:
                raise ValueError(f"Тег «{tag}» слишком длинный (максимум {MAX_TAG} символов)")
            if not TAG_PATTERN.match(tag):
                raise ValueError(
                    "Тег может содержать только буквы, цифры, пробел, дефис и подчёркивание"
                )
        return tags


class SectionCreate(BaseModel):
    """Создание раздела базы заготовок."""

    name: str = ""
    description: str = ""
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Название раздела обязательно")
        if len(cleaned) > MAX_SECTION_NAME:
            raise ValueError(f"Название раздела слишком длинное (максимум {MAX_SECTION_NAME} символов)")
        return cleaned

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) > MAX_SECTION_DESCRIPTION:
            raise ValueError(
                f"Описание слишком длинное (максимум {MAX_SECTION_DESCRIPTION} символов)"
            )
        return cleaned


class SectionUpdate(SectionCreate):
    """Правка раздела: набор полей совпадает с созданием."""


class SectionRead(BaseModel):
    """Раздел для шаблонов: данные раздела и число заготовок в нём."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    sort_order: int = 0
    created_at: datetime
    blocks_count: int = 0


class TagRead(BaseModel):
    """Тег заготовки."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class TemplateBlockCreate(_TagsForm):
    """Создание заготовки: раздел, заголовок, содержание и теги."""

    section_id: int = 0
    title: str = ""
    body: str = ""

    @field_validator("section_id")
    @classmethod
    def validate_section_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Выберите раздел для заготовки")
        return value

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Заголовок заготовки обязателен")
        if len(cleaned) > MAX_TITLE:
            raise ValueError(f"Заголовок слишком длинный (максимум {MAX_TITLE} символов)")
        return cleaned

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Содержание заготовки обязательно")
        return cleaned


class TemplateBlockUpdate(TemplateBlockCreate):
    """Правка заготовки: набор полей совпадает с созданием."""


class TemplateBlockRead(BaseModel):
    """Заготовка целиком: для страницы просмотра и формы правки."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    section_id: int
    section_name: str | None = None
    title: str
    body: str
    tags: list[TagRead] = []
    author_name: str | None = None
    created_at: datetime
    updated_at: datetime


class TemplateBlockListItem(BaseModel):
    """Облегчённое представление заготовки для карточки в списке."""

    id: int
    section_id: int
    section_name: str | None = None
    title: str
    body: str
    body_preview: str = ""
    tags: list[str] = []
    author_name: str | None = None
    updated_at: datetime
