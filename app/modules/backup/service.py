"""Ядро резервного копирования: сборка файла, чтение, диск и восстановление.

Модуль не знает ни одной таблицы: разделы приходят из реестра
(``registry.py``), поэтому новый модуль подключается к бэкапу без правок
этого файла.

Правила восстановления:

* режим один — «заменить всё»: данные портала становятся такими, как в копии;
* очистка таблиц идёт по убыванию ``order`` (от «детей» к «родителям»),
  вставка — по возрастанию; порядок задан внешними ключами;
* вся работа с БД — одна транзакция: любая ошибка раздела откатывает её
  целиком, поэтому база остаётся прежней;
* файлы Google (ключ, токен, почта) пишутся после фиксации БД: сбой записи
  файлов уже не откатывает данные, а попадает в предупреждения отчёта.

В журнал попадают только имена файлов и счётчики — никогда содержимое копии
и никогда секреты.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.modules.backup import registry
from app.modules.backup.registry import BackupValidationError, ordered_sections
from app.modules.backup.schemas import (
    BACKUP_FILE_PREFIX,
    BACKUP_FILE_SUFFIX,
    FORMAT_NAME,
    SUPPORTED_FORMAT_VERSION,
    BackupEnvelope,
    BackupFile,
    RestoreReport,
)

logger = logging.getLogger(__name__)


def _utc_stamp() -> str:
    """Время сборки копии в файле: UTC без пояса, ISO, до секунд."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _count_records(payload: Any) -> int:
    """Число записей раздела для предпросмотра.

    Плоский раздел считает строки (``rows``), составной — сумму записей всех
    своих списков. Раздел без таблиц (файлы Google) даёт 0.
    """
    if not isinstance(payload, dict):
        return 0
    rows = payload.get("rows")
    if isinstance(rows, list):
        return len(rows)
    return sum(
        len(value) for value in payload.values() if isinstance(value, list)
    )


async def build_backup(
    db: AsyncSession,
    *,
    include_plain_passwords: bool = False,
    include_google_credentials: bool = False,
) -> dict[str, Any]:
    """Собирает файл копии: огибающая с версией формата и данные разделов."""
    sections: dict[str, Any] = {}
    counts: dict[str, int] = {}
    with registry.export_options(
        include_plain_passwords=include_plain_passwords,
        include_google_credentials=include_google_credentials,
    ):
        for section in ordered_sections():
            data = await section.export(db)
            sections[section.key] = data
            counts[section.key] = _count_records(data)
    logger.info(
        "Резервная копия собрана: %s (пароли: %s, ключ Google: %s)",
        ", ".join(f"{key}={value}" for key, value in counts.items()),
        "да" if include_plain_passwords else "нет",
        "да" if include_google_credentials else "нет",
    )
    return {
        "format": FORMAT_NAME,
        "format_version": SUPPORTED_FORMAT_VERSION,
        "created_at": _utc_stamp(),
        "app_commit": None,
        "counts": counts,
        "sections": sections,
    }


def dumps(backup: dict[str, Any]) -> bytes:
    """Файл копии в байтах: UTF-8, отступы — файл читается глазами."""
    return json.dumps(backup, ensure_ascii=False, indent=2).encode("utf-8")


def load(data: bytes) -> dict[str, Any]:
    """Проверяет файл копии и возвращает его содержимое.

    Проверяется только оболочка: формат, версия и названия разделов.
    Содержимое раздела проверяет сам раздел при восстановлении — так же
    с русским текстом ошибки.
    """
    if not data:
        raise BackupValidationError("Файл резервной копии пуст")
    try:
        # utf-8-sig: файл могли сохранить из блокнота Windows с BOM
        raw = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupValidationError(
            "Файл не похож на резервную копию: это не JSON"
        ) from exc
    if not isinstance(raw, dict):
        raise BackupValidationError(
            "Файл не похож на резервную копию: ожидался объект JSON"
        )

    try:
        envelope = BackupEnvelope.model_validate(raw)
    except ValidationError as exc:
        first = str(exc.errors()[0].get("msg", "неверная структура"))
        raise BackupValidationError(
            f"Файл не похож на резервную копию: {first.removeprefix('Value error, ')}"
        ) from exc

    if envelope.format != FORMAT_NAME:
        raise BackupValidationError(
            f"Неизвестный формат копии: «{envelope.format}»"
        )
    if envelope.format_version < 1:
        raise BackupValidationError(
            f"Неверная версия формата копии: {envelope.format_version}"
        )
    if envelope.format_version > SUPPORTED_FORMAT_VERSION:
        raise BackupValidationError(
            "Копия сделана более новой версией портала "
            f"(версия формата {envelope.format_version}, "
            f"поддерживается {SUPPORTED_FORMAT_VERSION})"
        )

    sections = envelope.sections
    if not sections:
        raise BackupValidationError("В копии нет разделов с данными")
    known = registry.sections_by_key()
    unknown = sorted(set(sections) - set(known))
    if unknown:
        raise BackupValidationError(
            "В копии есть разделы, которых нет в этой версии портала: "
            + ", ".join(unknown)
        )
    for key, value in sections.items():
        if not isinstance(value, dict):
            raise BackupValidationError(
                f"Раздел «{known[key].title}» в копии повреждён: ожидался объект"
            )
    return raw


async def _restore_files(
    db: AsyncSession,
    present: list[registry.BackupSection],
    data_sections: dict[str, Any],
) -> bool:
    """Пишет файловые разделы после фиксации БД; сбой — только предупреждение."""
    file_sections = [section for section in present if section.after_commit]
    if not file_sections:
        return False
    restored = True
    for section in file_sections:
        try:
            await section.import_(db, data_sections[section.key])
        except BackupValidationError as exc:
            restored = False
            registry.warn(f"Раздел «{section.title}» не восстановлен: {exc}")
        except Exception as exc:  # noqa: BLE001 - сбой файлов не должен ронять БД
            restored = False
            logger.warning("Раздел «%s» не восстановлен: %s", section.title, exc)
            registry.warn(
                f"Раздел «{section.title}» не восстановлен: "
                f"{str(exc)[:200] or type(exc).__name__}"
            )
    return restored


async def restore_backup(
    db: AsyncSession,
    backup: dict[str, Any],
    *,
    mode: str = "replace",
) -> RestoreReport:
    """Заменяет данные портала данными копии в одной транзакции.

    Возвращает отчёт: сколько записей каждого раздела перенесено и какие
    предупреждения появились. Ошибка формата раздела (``BackupValidationError``)
    откатывает транзакцию — база остаётся прежней.
    """
    if mode != "replace":
        raise BackupValidationError(
            "Поддерживается только восстановление в режиме «заменить всё»"
        )

    data_sections = backup.get("sections")
    if not isinstance(data_sections, dict) or not data_sections:
        raise BackupValidationError("В копии нет разделов с данными")

    ordered = ordered_sections()
    present = [section for section in ordered if section.key in data_sections]
    missing = [section for section in ordered if section.key not in data_sections]
    report = RestoreReport(mode=mode)

    with registry.collect_warnings() as collected:
        for section in missing:
            registry.warn(
                f"Раздел «{section.title}» в копии отсутствует — "
                "его данные не тронуты."
            )
        try:
            # 1. Очистка: от «детей» к «родителям» — обратный порядок зависимостей
            for section in reversed(present):
                if section.after_commit or section.clear is None:
                    continue
                await section.clear(db)
            await db.flush()

            # 2. Вставка: строго по возрастанию order (users раньше карточек)
            for section in present:
                if section.after_commit:
                    continue
                await section.import_(db, data_sections[section.key])
                report.counts[section.key] = _count_records(
                    data_sections[section.key]
                )
            await db.commit()
        except BackupValidationError:
            await db.rollback()
            raise
        except Exception as exc:  # noqa: BLE001 - любую ошибку показываем нотариусу
            await db.rollback()
            logger.exception("Восстановление из резервной копии не выполнено")
            raise BackupValidationError(
                "Не удалось восстановить данные — база осталась прежней: "
                + (str(exc)[:200] or type(exc).__name__)
            ) from exc

        # 3. Файлы Google — после commit: их сбой БД уже не откатывает
        report.google_files_restored = await _restore_files(
            db, present, data_sections
        )

    report.warnings = list(collected)
    for warning in report.warnings:
        logger.warning("Восстановление из копии: %s", warning)
    logger.info(
        "Данные восстановлены из копии: %s",
        ", ".join(f"{key}={value}" for key, value in report.counts.items()) or "нет",
    )
    return report


def _backup_dir() -> Path:
    """Папка резервных копий из настроек: один каталог на весь портал."""
    return Path(get_settings().BACKUP_DIR)


def _write_file(payload: bytes) -> Path:
    """Пишет файл portal-backup-YYYYMMDD-HHMMSS.json (время сервера, локальное).

    Две копии в одну секунду не перетирают друг друга: к имени добавляется
    номер — ``portal-backup-20261031-140500-2.json``.
    """
    directory = _backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = directory / f"{BACKUP_FILE_PREFIX}{stamp}{BACKUP_FILE_SUFFIX}"
    counter = 2
    while path.exists():
        path = directory / f"{BACKUP_FILE_PREFIX}{stamp}-{counter}{BACKUP_FILE_SUFFIX}"
        counter += 1
    path.write_bytes(payload)
    return path


async def save_to_disk(backup: dict[str, Any]) -> Path:
    """Сохраняет копию в папку из настроек и возвращает путь к файлу."""
    path = await run_in_threadpool(_write_file, dumps(backup))
    logger.info("Резервная копия сохранена: %s (%d байт)", path.name, path.stat().st_size)
    return path


def _list_files() -> list[BackupFile]:
    """Файлы копий в папке: только свои имена, свежие — первыми."""
    directory = _backup_dir()
    if not directory.is_dir():
        return []
    files: list[BackupFile] = []
    for path in directory.iterdir():
        name = path.name
        if not path.is_file() or not name.startswith(BACKUP_FILE_PREFIX):
            continue
        if not name.endswith(BACKUP_FILE_SUFFIX):
            continue
        try:
            stat = path.stat()
        except OSError:
            # Файл успели удалить между перебором и чтением атрибутов
            continue
        files.append(
            BackupFile(
                name=name,
                size=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime),
            )
        )
    files.sort(key=lambda item: item.name, reverse=True)
    return files


async def list_backups() -> list[BackupFile]:
    """Список файлов копий в папке из настроек (новые сверху)."""
    return await run_in_threadpool(_list_files)


def _safe_name(name: str) -> str:
    """Проверяет имя файла копии: защита от ``../`` и абсолютных путей."""
    candidate = (name or "").strip()
    if not candidate or Path(candidate).name != candidate:
        raise BackupValidationError("Недопустимое имя файла резервной копии")
    if not candidate.startswith(BACKUP_FILE_PREFIX) or not candidate.endswith(
        BACKUP_FILE_SUFFIX
    ):
        raise BackupValidationError(
            "Недопустимое имя файла резервной копии: ожидается portal-backup-….json"
        )
    return candidate


def _read_file(name: str) -> bytes:
    """Читает файл копии по имени из папки из настроек."""
    path = _backup_dir() / _safe_name(name)
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise BackupValidationError(
            f"Файл «{name}» не найден в папке резервных копий"
        ) from exc
    except OSError as exc:
        raise BackupValidationError(
            f"Не удалось прочитать файл «{name}»: {exc.strerror or exc}"
        ) from exc


async def read_backup_file(name: str) -> bytes:
    """Байты файла копии; имя предварительно проверяется."""
    return await run_in_threadpool(_read_file, name)
