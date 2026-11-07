"""Сборка установщика портала: значок, Portal.exe (PyInstaller) и Setup.exe (Inno Setup).

Запуск из корня проекта:

    venv\\Scripts\\python.exe desktop\\build.py

Что делает скрипт:

1. проверяет и при необходимости доустанавливает пакеты из
   ``desktop/requirements-desktop.txt`` (PyInstaller, pystray, Pillow);
2. собирает ``desktop/portal.ico`` из ``logo.jpg``;
3. упаковывает ``desktop/launcher.py`` в ``desktop/dist/Portal/Portal.exe``;
4. кладёт рядом с exe шаблоны, статику и ``scripts/create_admin.py``
   (приложение подключает их относительными путями);
5. собирает установщик Inno Setup в ``desktop/output/Portal-Setup-<версия>.exe``.

Ключи:

* ``--version 1.2.0`` — версия установщика (по умолчанию ``1.2.0``);
* ``--skip-exe`` — не пересобирать Portal.exe, взять готовый из ``dist``;
* ``--skip-installer`` — остановиться на папке ``dist/Portal``;
* ``--install-inno`` — скачать и тихо установить Inno Setup, если его нет.
"""
import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

DESKTOP_DIR = Path(__file__).resolve().parent
ROOT = DESKTOP_DIR.parent
DIST_DIR = DESKTOP_DIR / "dist"
WORK_DIR = DESKTOP_DIR / "build"
OUTPUT_DIR = DESKTOP_DIR / "output"
APP_DIR = DIST_DIR / "Portal"
REQUIREMENTS = DESKTOP_DIR / "requirements-desktop.txt"
SPEC_FILE = DESKTOP_DIR / "portal.spec"
ISS_FILE = DESKTOP_DIR / "portal.iss"

# Откуда берётся Inno Setup, если его нет на компьютере
INNO_URL = (
    "https://github.com/jrsoftware/issrc/releases/download/is-6_7_4/innosetup-6.7.4.exe"
)
INNO_SEARCH_PATHS = (
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
)

# Файлы приложения, которые должны лежать рядом с Portal.exe, а не в _internal
COMPANION_ITEMS = (
    ("app/templates", "app/templates"),
    ("app/static", "app/static"),
    ("scripts/create_admin.py", "scripts/create_admin.py"),
)


def run(command: list[str], *, cwd: Path = ROOT) -> None:
    """Запускает внешнюю команду и падает с понятным текстом при ошибке."""
    print("+ " + " ".join(str(part) for part in command))
    result = subprocess.run(command, cwd=str(cwd))
    if result.returncode != 0:
        raise SystemExit(f"Команда завершилась с кодом {result.returncode}")


def ensure_requirements() -> None:
    """Ставит пакеты настольной сборки, если их нет в текущем окружении."""
    missing = []
    for module, package in (
        ("PyInstaller", "pyinstaller"),
        ("pystray", "pystray"),
        ("PIL", "pillow"),
    ):
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        print(f"Не хватает пакетов: {', '.join(missing)} — устанавливаю")
        run([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    else:
        print("Пакеты настольной сборки на месте")


def build_icon() -> None:
    """Собирает portal.ico из logo.jpg."""
    sys.path.insert(0, str(DESKTOP_DIR))
    import make_icon  # noqa: PLC0415 — модуль сборки лежит рядом

    print(f"Значок: {make_icon.build_icon()}")


def build_exe() -> None:
    """Упаковывает приложение PyInstaller'ом в desktop/dist/Portal."""
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(DIST_DIR),
            "--workpath",
            str(WORK_DIR),
            str(SPEC_FILE),
        ]
    )


def copy_companions() -> None:
    """Кладёт шаблоны, статику и служебные файлы рядом с Portal.exe."""
    exe = APP_DIR / "Portal.exe"
    if not exe.exists():
        raise SystemExit(f"Нет собранного приложения: {exe}")
    for source_rel, target_rel in COMPANION_ITEMS:
        source = ROOT / source_rel
        target = APP_DIR / target_rel
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    # Значок нужен значку в трее, логотип — странице входа в браузере
    for source in (DESKTOP_DIR / "portal.ico", ROOT / "logo.jpg"):
        if source.exists():
            shutil.copy2(source, APP_DIR / source.name)
    print(f"Файлы приложения готовы: {APP_DIR}")


def find_inno() -> Path | None:
    """Ищет компилятор Inno Setup: PATH, затем обычные папки установки."""
    found = shutil.which("ISCC") or shutil.which("iscc")
    if found:
        return Path(found)
    for candidate in INNO_SEARCH_PATHS:
        if candidate.exists():
            return candidate
    return None


def install_inno() -> Path | None:
    """Скачивает установщик Inno Setup и ставит его тихо в профиль пользователя."""
    target = Path(os.environ.get("TEMP", ".")) / "innosetup-portal.exe"
    print(f"Скачиваю Inno Setup: {INNO_URL}")
    urllib.request.urlretrieve(INNO_URL, target)
    run(
        [
            str(target),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/CURRENTUSER",
            "/SP-",
        ]
    )
    return find_inno()


def build_installer(version: str) -> Path:
    """Собирает установщик Inno Setup из desktop/portal.iss."""
    compiler = find_inno()
    if compiler is None:
        raise SystemExit(
            "Не найден компилятор Inno Setup (ISCC.exe).\n"
            "Установите Inno Setup 6 или запустите сборку с ключом --install-inno."
        )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run([str(compiler), f"/DAppVersion={version}", str(ISS_FILE)], cwd=DESKTOP_DIR)
    setup = OUTPUT_DIR / f"Portal-Setup-{version}.exe"
    if not setup.exists():
        raise SystemExit(f"Установщик не создан: {setup}")
    return setup


def main(argv: list[str] | None = None) -> int:
    """Выполняет шаги сборки по порядку и печатает путь к готовому установщику."""
    parser = argparse.ArgumentParser(description="Сборка установщика портала")
    parser.add_argument("--version", default="1.2.0", help="версия установщика")
    parser.add_argument("--skip-exe", action="store_true", help="не пересобирать Portal.exe")
    parser.add_argument(
        "--skip-installer", action="store_true", help="только папка dist/Portal"
    )
    parser.add_argument(
        "--install-inno", action="store_true", help="установить Inno Setup, если его нет"
    )
    args = parser.parse_args(argv)

    ensure_requirements()
    build_icon()
    if args.skip_exe:
        print("Portal.exe не пересобирается (--skip-exe)")
    else:
        build_exe()
    copy_companions()

    if args.skip_installer:
        print(f"Готово: {APP_DIR}")
        return 0

    if args.install_inno and find_inno() is None:
        install_inno()
    setup = build_installer(args.version)
    print(f"Установщик готов: {setup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
