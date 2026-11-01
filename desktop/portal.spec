# -*- mode: python ; coding: utf-8 -*-
"""Сборка настольного приложения портала (PyInstaller).

Запускается из ``desktop/build.py``. Результат — папка ``desktop/dist/Portal``:
``Portal.exe`` без консоли, ``_internal`` с библиотеками и рядом копии
``app/templates``, ``app/static``, ``scripts/create_admin.py``, ``portal.ico``.
Приложение подключает шаблоны и статику относительными путями, поэтому копии
кладутся именно рядом с exe, а не внутрь ``_internal``.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

DESKTOP_DIR = Path(SPECPATH).resolve()  # noqa: F821 — путь к этому файлу даёт PyInstaller
ROOT = DESKTOP_DIR.parent

# Модули, которые подключаются по строке и потому не видны статическому анализу
hiddenimports = [
    "app.main",
    # uvicorn выбирает цикл событий и протокол по строковому имени
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    # Разбор форм FastAPI подключает python-multipart при первом запросе
    "multipart",
    "multipart.multipart",
    "python_multipart",
    "python_multipart.multipart",
    # SQLAlchemy подключает диалект и драйвер по строке из DATABASE_URL
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.aiosqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
    # Асинхронный драйвер и greenlet: SQLAlchemy загружает их через importlib
    "aiosqlite",
    "aiosqlite.core",
    "greenlet",
    # passlib ищет обработчики паролей по имени схемы («bcrypt»)
    "passlib.handlers.bcrypt",
    "passlib.handlers.bcrypt._bcrypt",
    "passlib.crypto._md4",
    # Значок в трее: pystray выбирает backend по платформе
    "pystray._win32",
    "PIL.Image",
    "PIL.ImageDraw",
]

# Пакеты с внутренними подмодулями, которые подключаются динамически
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("passlib")
hiddenimports += collect_submodules("googleapiclient.discovery")
hiddenimports += collect_submodules("googleapiclient.http")

a = Analysis(
    [str(DESKTOP_DIR / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # tkinter в портале не используется: без него сборка легче на ~10 МБ
    excludes=["tkinter", "pytest", "alembic"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Portal",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=str(DESKTOP_DIR / "portal.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Portal",
)
