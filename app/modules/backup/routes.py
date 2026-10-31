"""Маршруты раздела «Настройки → Резервное копирование».

Доступ — только нотариусу (роль ``admin``), как у остальных разделов
настроек. Адреса начинаются с ``/settings/backup``: роутер подключается
в ``app/main.py`` без префикса — так же, как роутер настроек, у которого
пути прописаны целиком.

Создание копии и восстановление не пишут загруженный файл на диск:
восстановление читает байты в память (предел — ``MAX_BACKUP_SIZE``),
поэтому в папке ``backups/`` появляются только копии, собранные порталом.
"""
import logging
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.templating import render
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User
from app.modules.backup import service
from app.modules.backup.registry import BackupValidationError
from app.modules.backup.schemas import MAX_BACKUP_SIZE
from app.modules.settings.routes import MENU_SETTINGS

logger = logging.getLogger(__name__)

# Описания маршрутов для документации FastAPI
router = APIRouter(tags=["backup"])

# Текущий пользователь с ролью нотариуса
AdminUser = Annotated[User, Depends(require_role("admin"))]

# Адрес раздела и значение settings_section для меню настроек
BACKUP_URL = "/settings/backup"
SETTINGS_BACKUP = "backup"


async def _render_page(
    request: Request,
    user: User | None,
    *,
    message: str | None = None,
    warn_message: str | None = None,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Рендерит страницу настроек с разделом «Резервное копирование»."""
    directory = Path(get_settings().BACKUP_DIR)
    try:
        absolute = str(directory.resolve())
    except OSError:
        # Каталог ещё не создан или путь недоступен — показываем как задан
        absolute = str(directory)
    return render(
        request,
        "settings/index.html",
        user=user,
        active_menu=MENU_SETTINGS,
        settings_section=SETTINGS_BACKUP,
        backup_url=BACKUP_URL,
        backup_files=await service.list_backups(),
        backup_dir=str(directory),
        backup_dir_absolute=absolute,
        message=message,
        warn_message=warn_message,
        error=error,
        status_code=status_code,
    )


async def _reload_user(db: AsyncSession, user_id: int) -> User | None:
    """Перечитывает нотариуса по id после rollback.

    ``restore_backup`` при ошибке откатывает транзакцию, и объекты сессии
    становятся просроченными: обращение к ``user.full_name`` (в том числе
    к ``user.id``) полезло бы в БД синхронно и упало. Поэтому id запоминается
    до восстановления, а страница ошибки рисуется по свежей записи.
    """
    return await db.get(User, user_id)


def _page_messages(
    *,
    created: str | None,
    restored: str | None,
    saved: str | None,
    warn: int,
) -> tuple[str | None, str | None]:
    """Тексты сообщений по флагам в адресе: что сделали и о чём предупредить."""
    message: str | None = None
    if created:
        message = (
            f"Копия создана: {created}. Файл лежит в папке резервных копий — "
            "его можно скачать или оставить на компьютере портала."
        )
    elif restored:
        saved_note = f" Прежнее состояние сохранено в файл {saved}." if saved else ""
        message = (
            f"Данные восстановлены из копии: {restored}.{saved_note} "
            "Войдите заново, если ваша учётная запись была изменена."
        )
    warn_message = (
        (
            f"Восстановление выполнено с предупреждениями ({warn}). "
            "Подробности — в журнале сервера."
        )
        if warn
        else None
    )
    return message, warn_message


@router.get("/settings/backup", response_class=HTMLResponse, response_model=None)
async def settings_backup_page(
    request: Request,
    user: AdminUser,
    created: str | None = None,
    restored: str | None = None,
    saved: str | None = None,
    warn: int = 0,
    error: str | None = None,
) -> HTMLResponse:
    """Раздел «Резервное копирование»: создание копии, файлы в папке, восстановление."""
    message, warn_message = _page_messages(
        created=created, restored=restored, saved=saved, warn=warn
    )
    return await _render_page(
        request,
        user,
        message=message,
        warn_message=warn_message,
        error=error,
    )


@router.get("/settings/backup/files", response_model=None)
async def settings_backup_files(user: AdminUser) -> JSONResponse:
    """Список файлов копий в формате JSON: имя, размер и дата для таблицы."""
    files = await service.list_backups()
    return JSONResponse(
        {
            "files": [
                {
                    "name": item.name,
                    "size": item.size,
                    "size_label": item.size_label,
                    "created": item.created_label,
                }
                for item in files
            ]
        }
    )


@router.get("/settings/backup/download/{name}", response_model=None)
async def settings_backup_download(user: AdminUser, name: str) -> Response:
    """Отдаёт файл копии как вложение: браузер сохранит его на компьютер."""
    try:
        payload = await service.read_backup_file(name)
    except BackupValidationError as exc:
        logger.warning("Файл копии не выдан: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    logger.info("Резервная копия выдана на скачивание: %s", Path(name).name)
    return Response(
        content=payload,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                "attachment; filename*=UTF-8''" + quote(Path(name).name)
            )
        },
    )


@router.post("/settings/backup/create", response_model=None)
async def settings_backup_create(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
    include_plain_passwords: Annotated[bool, Form()] = False,
    include_google_credentials: Annotated[bool, Form()] = False,
) -> HTMLResponse | RedirectResponse:
    """Собирает копию по реестру разделов и кладёт файл в папку из настроек."""
    try:
        backup = await service.build_backup(
            db,
            include_plain_passwords=include_plain_passwords,
            include_google_credentials=include_google_credentials,
        )
        path = await service.save_to_disk(backup)
    except BackupValidationError as exc:
        return await _render_page(
            request, user, error=str(exc), status_code=status.HTTP_400_BAD_REQUEST
        )
    except OSError as exc:
        logger.warning("Не удалось сохранить резервную копию: %s", exc)
        return await _render_page(
            request,
            user,
            error=(
                "Не удалось сохранить файл резервной копии: "
                + (exc.strerror or str(exc))
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(
        f"{BACKUP_URL}?created={quote(path.name)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


async def _restore_source(
    file: UploadFile | None,
    name: str | None,
) -> tuple[bytes, str]:
    """Байты копии и её имя: файл из папки или загруженный файл.

    Загруженный файл читается в память с пределом ``MAX_BACKUP_SIZE`` и на
    диск не пишется: в папке копий появляются только файлы, собранные порталом.
    """
    if name and name.strip():
        selected = name.strip()
        return await service.read_backup_file(selected), selected
    if file is None or not file.filename:
        raise BackupValidationError(
            "Выберите файл резервной копии или файл из папки"
        )
    # Читаем на байт больше предела: так видно, что файл превышает допустимый
    raw = await file.read(MAX_BACKUP_SIZE + 1)
    if not raw:
        raise BackupValidationError("Загруженный файл пуст")
    if len(raw) > MAX_BACKUP_SIZE:
        raise BackupValidationError(
            f"Файл больше {MAX_BACKUP_SIZE // (1024 * 1024)} МБ — это не копия портала"
        )
    return raw, Path(file.filename).name


@router.post("/settings/backup/restore", response_class=HTMLResponse, response_model=None)
async def settings_backup_restore(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
    file: Annotated[UploadFile | None, File()] = None,
    name: Annotated[str | None, Form()] = None,
    mode: Annotated[str, Form()] = "replace",
) -> HTMLResponse | RedirectResponse:
    """Заменяет данные портала данными копии, сохраняя автобэкап прежнего состояния.

    Порядок: прочитать файл → сохранить копию текущего состояния (со всеми
    секретами) → проверить файл и восстановить его в одной транзакции.
    Автобэкап делается до разбора файла: даже отклонённая копия не оставляет
    нотариуса без свежего снимка данных. Ошибка копии базу не меняет.
    """
    # id запоминаем до восстановления: после rollback объект user просрочен
    user_id = user.id
    try:
        raw, source = await _restore_source(file, name)
        auto_backup = await service.save_to_disk(
            await service.build_backup(
                db,
                include_plain_passwords=True,
                include_google_credentials=True,
            )
        )
        backup = service.load(raw)
        report = await service.restore_backup(db, backup, mode=mode)
    except BackupValidationError as exc:
        logger.warning("Восстановление отклонено: %s", exc)
        return await _render_page(
            request,
            await _reload_user(db, user_id),
            error=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except OSError as exc:
        logger.warning("Не удалось сохранить автобэкап перед восстановлением: %s", exc)
        return await _render_page(
            request,
            await _reload_user(db, user_id),
            error=(
                "Не удалось сохранить копию текущего состояния — "
                "восстановление отменено: "
                + (exc.strerror or str(exc))
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    params = f"restored={quote(source)}&saved={quote(auto_backup.name)}"
    if report.warnings:
        params += f"&warn={len(report.warnings)}"
    return RedirectResponse(
        f"{BACKUP_URL}?{params}", status_code=status.HTTP_303_SEE_OTHER
    )
