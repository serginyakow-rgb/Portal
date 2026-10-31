"""Схемы формата файла резервной копии и отчёт о восстановлении.

Файл — обычный JSON (не ZIP и не дамп SQLite): его читают глазами, он
собирается стандартной библиотекой, а версия формата задана явным полем —
поэтому добавление нового раздела не ломает старые копии.

Структура корня::

    {
      "format": "notary-portal-backup",
      "format_version": 1,
      "created_at": "2026-10-31T14:05:00",
      "app_commit": null,
      "counts": {"users": 4, "tasks": 7, ...},
      "sections": {"users": {"rows": [...]}, ...}
    }
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel

# Имя формата: по нему файл узнаётся среди прочих JSON
FORMAT_NAME = "notary-portal-backup"

# Версия формата, которую умеет читать портал
SUPPORTED_FORMAT_VERSION = 1

# Имя файла копии: portal-backup-YYYYMMDD-HHMMSS.json
BACKUP_FILE_PREFIX = "portal-backup-"
BACKUP_FILE_SUFFIX = ".json"

# Предел размера загружаемого файла восстановления (20 МБ)
MAX_BACKUP_SIZE = 20 * 1024 * 1024


class BackupEnvelope(BaseModel):
    """Огибающая часть файла копии: версия формата, время сборки, разделы.

    Поля ``counts`` и ``app_commit`` нужны для предпросмотра и диагностики;
    при восстановлении они не используются.
    """

    format: str
    format_version: int
    created_at: str = ""
    app_commit: str | None = None
    counts: dict[str, int] = {}
    sections: dict[str, Any] = {}


@dataclass(frozen=True)
class BackupFile:
    """Файл резервной копии в папке ``backups/``."""

    name: str
    size: int
    modified_at: datetime

    @property
    def size_label(self) -> str:
        """Размер для таблицы: «512 Б», «4,2 КБ», «1,3 МБ»."""
        if self.size < 1024:
            return f"{self.size} Б"
        if self.size < 1024 * 1024:
            return f"{self.size / 1024:.1f} КБ".replace(".", ",")
        return f"{self.size / (1024 * 1024):.1f} МБ".replace(".", ",")

    @property
    def created_label(self) -> str:
        """Дата файла для таблицы: «31.10.2026 14:05»."""
        return self.modified_at.strftime("%d.%m.%Y %H:%M")


@dataclass
class RestoreReport:
    """Итог восстановления: что перенесено, что пропущено и почему."""

    mode: str
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    # Файлы Google (ключ, токен, почта) записаны на место
    google_files_restored: bool = False
