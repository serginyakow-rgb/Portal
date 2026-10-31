"""Контракт раздела резервной копии и реестр разделов.

Ядро резервного копирования (``service.py``) не знает ни одной конкретной
таблицы: оно перебирает зарегистрированные разделы и вызывает их ``export``
и ``import_``. Поэтому новый модуль подключается к бэкапу одной записью —
``register(BackupSection(...))`` — и ядро при этом не правится.

Порядок ``order`` задаёт и вставку, и удаление:

* выгрузка и восстановление идут по возрастанию ``order``;
* очистка таблиц — по убыванию ``order``, поэтому раздел, чьи строки
  ссылаются на ``users.id`` (карточки «Задач», заготовки «Базы данных»),
  обязан иметь ``order`` больше, чем у раздела ``users``.

Поля раздела:

* ``key`` — ключ в файле копии и в отчёте (``users``, ``tasks``, ...);
* ``title`` — подпись раздела для сообщений нотариусу;
* ``order`` — место в порядке выгрузки/восстановления (см. выше);
* ``export`` — выгрузка: возвращает обычные словари и списки, пригодные
  для ``json.dumps`` без своих кодировщиков (даты — строки ISO);
* ``import_`` — восстановление: получает УЖЕ проверенный словарь раздела
  (ядро проверило, что это объект), пишет только через ORM и сохраняет
  идентификаторы — на них ссылаются внешние ключи. При несоответствии
  формы бросает ``BackupValidationError`` с русским текстом; транзакцию
  откатывает ядро;
* ``clear`` — удаление своих строк перед вставкой (порядок таблиц внутри
  раздела — забота самого раздела); ``None`` — у раздела нет таблиц;
* ``after_commit`` — раздел пишет файлы, а не таблицы: его ``clear``
  не вызывается, а ``import_`` выполняется после фиксации БД, чтобы сбой
  записи файлов не откатывал уже применённые данные.

Как подключить новый раздел к резервной копии (правило проекта,
``PROJECT_MAP.md`` §9):

1. создать ``app/modules/<модуль>/backup.py``: описать ``BackupSection``
   и вызвать ``register(...)`` при импорте модуля;
2. добавить в ``app/main.py`` один импорт рядом с импортами моделей:
   ``from app.modules import <модуль> as <модуль>_backup  # noqa: F401``
   (если модуль ещё не импортируется в ``main.py``);
3. ничего не менять в ``service.py``.

Флаги выгрузки (открытые пароли, ключ и токен Google) раздел получает через
``options()``: ядро выставляет их на время сборки файла, поэтому сигнатура
``export`` остаётся одинаковой у всех разделов. Предупреждения, которые
раздел хочет показать нотариусу после восстановления, он добавляет через
``warn()`` — ядро собирает их в отчёт.
"""
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


class BackupValidationError(ValueError):
    """Ошибка формата или содержимого копии: текст показывается нотариусу."""


@dataclass(frozen=True)
class BackupSection:
    """Раздел резервной копии: как выгрузить и как восстановить свои данные."""

    key: str
    title: str
    order: int
    export: Callable[[AsyncSession], Awaitable[dict[str, Any]]]
    import_: Callable[[AsyncSession, dict[str, Any]], Awaitable[None]]
    # Удаление своих строк перед вставкой; None — таблиц у раздела нет
    clear: Callable[[AsyncSession], Awaitable[None]] | None = None
    # Раздел пишет файлы, а не таблицы: восстановление — после commit БД
    after_commit: bool = False


# Зарегистрированные разделы: заполняется функцией register()
SECTIONS: list[BackupSection] = []


def register(section: BackupSection) -> None:
    """Добавляет раздел в реестр; повторный ключ — ошибка разработчика."""
    if any(existing.key == section.key for existing in SECTIONS):
        raise ValueError(f"Раздел резервной копии «{section.key}» уже зарегистрирован")
    SECTIONS.append(section)


def ordered_sections() -> list[BackupSection]:
    """Разделы в порядке зависимостей: сначала users, файлы Google — последними."""
    return sorted(SECTIONS, key=lambda item: (item.order, item.key))


def sections_by_key() -> dict[str, BackupSection]:
    """Реестр в виде словаря «ключ → раздел» — для проверки файла копии."""
    return {section.key: section for section in ordered_sections()}


# Параметры текущей выгрузки: ядро выставляет их на время сборки файла
_EXPORT_OPTIONS: ContextVar[Mapping[str, Any]] = ContextVar(
    "backup_export_options", default={}
)


@contextmanager
def export_options(**options: Any) -> Iterator[None]:
    """Выставляет флаги выгрузки для всех разделов на время сборки файла."""
    token = _EXPORT_OPTIONS.set(dict(options))
    try:
        yield
    finally:
        _EXPORT_OPTIONS.reset(token)


def options() -> Mapping[str, Any]:
    """Флаги текущей выгрузки: например ``include_plain_passwords``."""
    return _EXPORT_OPTIONS.get()


# Накопитель предупреждений раздела: показывает себя только внутри restore_backup()
_COLLECTED_WARNINGS: ContextVar[list[str] | None] = ContextVar(
    "backup_warnings", default=None
)


@contextmanager
def collect_warnings() -> Iterator[list[str]]:
    """Собирает предупреждения разделов на время восстановления."""
    collected: list[str] = []
    token = _COLLECTED_WARNINGS.set(collected)
    try:
        yield collected
    finally:
        _COLLECTED_WARNINGS.reset(token)


def warn(message: str) -> None:
    """Добавляет предупреждение в отчёт; вне восстановления — ничего не делает."""
    collected = _COLLECTED_WARNINGS.get()
    if collected is not None:
        collected.append(message)
