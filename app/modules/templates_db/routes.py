"""Маршруты модуля «База данных»: разделы, заготовки, поиск, копирование и удаление.

Префикс адресов (/templates-db) задаётся при подключении роутера в app/main.py,
поэтому внутри модуля пути указаны без префикса.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.templating import render
from app.modules.auth.dependencies import CurrentUser
from app.modules.auth.models import User
from app.modules.templates_db.models import Section
from app.modules.templates_db.schemas import (
    SectionCreate,
    SectionRead,
    SectionUpdate,
    TemplateBlockCreate,
    TemplateBlockRead,
    TemplateBlockUpdate,
)
from app.modules.templates_db.service import (
    SectionNotEmptyError,
    create_block,
    create_section,
    delete_block,
    delete_section,
    get_block,
    get_section,
    get_section_by_name,
    list_blocks,
    list_sections,
    read_block,
    update_block,
    update_section,
)

router = APIRouter(tags=["templates_db"])

# Значение active_menu для подсветки пункта «База данных» в левом меню
MENU_TEMPLATES_DB = "templates_db"


def _to_int(value: str) -> int:
    """Преобразует значение формы в число: пустая строка и мусор дают 0."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _validation_message(exc: ValidationError) -> str:
    """Возвращает первое сообщение об ошибке валидации в читаемом виде."""
    message = str(exc.errors()[0].get("msg", "Некорректные данные"))
    return message.removeprefix("Value error, ")


async def _render_index(
    request: Request,
    db: AsyncSession,
    user: User,
    *,
    section_id: int | None = None,
    tag: str | None = None,
    query: str | None = None,
    error: str | None = None,
    saved: bool = False,
    deleted: bool = False,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит страницу базы: слева разделы, справа заготовки и результаты поиска."""
    sections = await list_sections(db)
    active_section = next((item for item in sections if item.id == section_id), None)
    return render(
        request,
        "templates_db/index.html",
        user=user,
        active_menu=MENU_TEMPLATES_DB,
        sections=sections,
        blocks=await list_blocks(db, section_id=section_id, tag=tag, query=query),
        section_id=section_id,
        active_section=active_section,
        tag=tag or "",
        q=query or "",
        error=error,
        saved=saved,
        deleted=deleted,
        status_code=status_code,
    )


@router.get("/", response_class=HTMLResponse, response_model=None)
async def index_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    section_id: int | None = None,
    saved: bool = False,
    deleted: bool = False,
) -> HTMLResponse:
    """Главная страница базы заготовок: разделы и список заготовок."""
    return await _render_index(
        request,
        db,
        user,
        section_id=section_id,
        saved=saved,
        deleted=deleted,
    )


@router.get("/search", response_class=HTMLResponse, response_model=None)
async def search_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    section_id: int | None = None,
    tag: str | None = None,
    q: str | None = None,
) -> HTMLResponse:
    """Поиск заготовок: по разделу, по тегу и по тексту (заголовок и содержание)."""
    return await _render_index(request, db, user, section_id=section_id, tag=tag, query=q)


def _render_section_form(
    request: Request,
    user: User,
    *,
    section: Section | None = None,
    name: str = "",
    description: str = "",
    sort_order: int = 0,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит форму раздела: создание и правку."""
    return render(
        request,
        "templates_db/section_form.html",
        user=user,
        active_menu=MENU_TEMPLATES_DB,
        section=section,
        name=name,
        description=description,
        sort_order=sort_order,
        error=error,
        status_code=status_code,
    )


@router.get("/sections/new", response_class=HTMLResponse, response_model=None)
async def section_new_form(request: Request, user: CurrentUser) -> HTMLResponse:
    """Форма создания раздела."""
    return _render_section_form(request, user)


@router.post("/sections/new", response_class=HTMLResponse, response_model=None)
async def section_new(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    name: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    sort_order: Annotated[str, Form()] = "0",
) -> HTMLResponse | RedirectResponse:
    """Создаёт раздел базы заготовок."""
    try:
        data = SectionCreate(
            name=name,
            description=description,
            sort_order=_to_int(sort_order),
        )
    except ValidationError as exc:
        return _render_section_form(
            request,
            user,
            name=name,
            description=description,
            sort_order=_to_int(sort_order),
            error=_validation_message(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if await get_section_by_name(db, data.name) is not None:
        return _render_section_form(
            request,
            user,
            name=name,
            description=description,
            sort_order=_to_int(sort_order),
            error=f"Раздел «{data.name}» уже существует",
            status_code=status.HTTP_409_CONFLICT,
        )

    try:
        await create_section(db, data)
    except IntegrityError:
        # Страховка от гонки, если то же название успел создать другой сотрудник
        await db.rollback()
        # Откат помечает объекты сессии устаревшими: пользователя перечитываем
        await db.refresh(user)
        return _render_section_form(
            request,
            user,
            name=name,
            description=description,
            sort_order=_to_int(sort_order),
            error=f"Раздел «{data.name}» уже существует",
            status_code=status.HTTP_409_CONFLICT,
        )

    return RedirectResponse("/templates-db/?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/sections/{section_id}/edit", response_class=HTMLResponse, response_model=None)
async def section_edit_form(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    section_id: int,
) -> HTMLResponse:
    """Форма правки раздела."""
    section = await get_section(db, section_id)
    if section is None:
        return await _render_index(
            request,
            db,
            user,
            error="Раздел не найден",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return _render_section_form(
        request,
        user,
        section=section,
        name=section.name,
        description=section.description or "",
        sort_order=section.sort_order,
    )


@router.post("/sections/{section_id}/edit", response_class=HTMLResponse, response_model=None)
async def section_edit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    section_id: int,
    name: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    sort_order: Annotated[str, Form()] = "0",
) -> HTMLResponse | RedirectResponse:
    """Сохраняет изменения раздела."""
    section = await get_section(db, section_id)
    if section is None:
        return await _render_index(
            request,
            db,
            user,
            error="Раздел не найден",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    try:
        data = SectionUpdate(
            name=name,
            description=description,
            sort_order=_to_int(sort_order),
        )
    except ValidationError as exc:
        return _render_section_form(
            request,
            user,
            section=section,
            name=name,
            description=description,
            sort_order=_to_int(sort_order),
            error=_validation_message(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    existing = await get_section_by_name(db, data.name)
    if existing is not None and existing.id != section.id:
        return _render_section_form(
            request,
            user,
            section=section,
            name=name,
            description=description,
            sort_order=_to_int(sort_order),
            error=f"Раздел «{data.name}» уже существует",
            status_code=status.HTTP_409_CONFLICT,
        )

    try:
        await update_section(db, section, data)
    except IntegrityError:
        # Страховка от гонки, если то же название успел создать другой сотрудник
        await db.rollback()
        # Откат помечает объекты сессии устаревшими: пользователя перечитываем
        await db.refresh(user)
        return _render_section_form(
            request,
            user,
            section=section,
            name=name,
            description=description,
            sort_order=_to_int(sort_order),
            error=f"Раздел «{data.name}» уже существует",
            status_code=status.HTTP_409_CONFLICT,
        )

    return RedirectResponse("/templates-db/?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/sections/{section_id}/delete", response_class=HTMLResponse, response_model=None)
async def section_delete(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    section_id: int,
) -> HTMLResponse | RedirectResponse:
    """Удаляет раздел: раздел с заготовками удалить нельзя."""
    section = await get_section(db, section_id)
    if section is None:
        return await _render_index(
            request,
            db,
            user,
            error="Раздел не найден",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    try:
        await delete_section(db, section)
    except SectionNotEmptyError as exc:
        return await _render_index(
            request,
            db,
            user,
            error=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse("/templates-db/?deleted=1", status_code=status.HTTP_303_SEE_OTHER)


def _render_block_form(
    request: Request,
    user: User,
    *,
    sections: list[SectionRead],
    block: TemplateBlockRead | None = None,
    section_id: int = 0,
    title: str = "",
    body: str = "",
    tags: str = "",
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит форму заготовки: создание и правку."""
    return render(
        request,
        "templates_db/block_form.html",
        user=user,
        active_menu=MENU_TEMPLATES_DB,
        sections=sections,
        block=block,
        section_id=section_id,
        title=title,
        body=body,
        tags=tags,
        error=error,
        status_code=status_code,
    )


def _pick_section_id(sections: list[SectionRead], section_id: int | None) -> int:
    """Выбирает раздел для формы: запрошенный, а при его отсутствии — первый."""
    if section_id is not None and any(item.id == section_id for item in sections):
        return section_id
    return sections[0].id if sections else 0


@router.get("/blocks/new", response_class=HTMLResponse, response_model=None)
async def block_new_form(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    section_id: int | None = None,
) -> HTMLResponse:
    """Форма создания заготовки: раздел можно задать заранее в адресе."""
    sections = await list_sections(db)
    if not sections:
        return await _render_index(
            request,
            db,
            user,
            error="Сначала создайте хотя бы один раздел базы заготовок",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return _render_block_form(
        request,
        user,
        sections=sections,
        section_id=_pick_section_id(sections, section_id),
    )


@router.post("/blocks/new", response_class=HTMLResponse, response_model=None)
async def block_new(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    section_id: Annotated[str, Form()] = "",
    title: Annotated[str, Form()] = "",
    body: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Создаёт заготовку: новые теги добавляются в базу автоматически."""
    sections = await list_sections(db)
    try:
        data = TemplateBlockCreate(
            section_id=_to_int(section_id),
            title=title,
            body=body,
            tags=tags,
        )
    except ValidationError as exc:
        return _render_block_form(
            request,
            user,
            sections=sections,
            section_id=_to_int(section_id),
            title=title,
            body=body,
            tags=tags,
            error=_validation_message(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if all(item.id != data.section_id for item in sections):
        return _render_block_form(
            request,
            user,
            sections=sections,
            title=title,
            body=body,
            tags=tags,
            error="Выбранный раздел не найден",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    await create_block(db, data, created_by=user.id)
    return RedirectResponse("/templates-db/?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/blocks/{block_id}", response_class=HTMLResponse, response_model=None)
async def block_view(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    block_id: int,
    saved: bool = False,
) -> HTMLResponse:
    """Страница просмотра заготовки: полный текст и кнопка копирования."""
    block = await read_block(db, block_id)
    if block is None:
        return await _render_index(
            request,
            db,
            user,
            error="Заготовка не найдена",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return render(
        request,
        "templates_db/block_view.html",
        user=user,
        active_menu=MENU_TEMPLATES_DB,
        block=block,
        saved=saved,
    )


@router.get("/blocks/{block_id}/edit", response_class=HTMLResponse, response_model=None)
async def block_edit_form(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    block_id: int,
) -> HTMLResponse:
    """Форма правки заготовки: раздел, заголовок, теги и текст."""
    block = await read_block(db, block_id)
    if block is None:
        return await _render_index(
            request,
            db,
            user,
            error="Заготовка не найдена",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return _render_block_form(
        request,
        user,
        sections=await list_sections(db),
        block=block,
        section_id=block.section_id,
        title=block.title,
        body=block.body,
        tags=", ".join(tag.name for tag in block.tags),
    )


@router.post("/blocks/{block_id}/edit", response_class=HTMLResponse, response_model=None)
async def block_edit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    block_id: int,
    section_id: Annotated[str, Form()] = "",
    title: Annotated[str, Form()] = "",
    body: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Сохраняет правку заготовки и пересобирает её теги."""
    block = await get_block(db, block_id)
    if block is None:
        return await _render_index(
            request,
            db,
            user,
            error="Заготовка не найдена",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    sections = await list_sections(db)
    try:
        data = TemplateBlockUpdate(
            section_id=_to_int(section_id),
            title=title,
            body=body,
            tags=tags,
        )
    except ValidationError as exc:
        return _render_block_form(
            request,
            user,
            sections=sections,
            block=await read_block(db, block_id),
            section_id=_to_int(section_id),
            title=title,
            body=body,
            tags=tags,
            error=_validation_message(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if all(item.id != data.section_id for item in sections):
        return _render_block_form(
            request,
            user,
            sections=sections,
            block=await read_block(db, block_id),
            title=title,
            body=body,
            tags=tags,
            error="Выбранный раздел не найден",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    await update_block(db, block, data)
    return RedirectResponse("/templates-db/?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/blocks/{block_id}/delete", response_class=HTMLResponse, response_model=None)
async def block_delete(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    block_id: int,
) -> HTMLResponse | RedirectResponse:
    """Удаляет заготовку из базы заготовок."""
    block = await get_block(db, block_id)
    if block is None:
        return await _render_index(
            request,
            db,
            user,
            error="Заготовка не найдена",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    await delete_block(db, block)
    return RedirectResponse("/templates-db/?deleted=1", status_code=status.HTTP_303_SEE_OTHER)
