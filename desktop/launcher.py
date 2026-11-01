"""Портал нотариальной конторы как настольное приложение: сервер и значок в трее.

Установщик кладёт рядом с ``Portal.exe`` само приложение (``app/``), шаблоны,
статику и служебные файлы. При запуске этот модуль:

1. переходит в папку программы — от неё считаются ``portal.db``, ``backups/``,
   ``.env`` и ``config/google_calendar/`` (все пути в проекте относительные);
2. при первом запуске создаёт ``.env`` со случайным ``SECRET_KEY`` и заводит
   учётную запись нотариуса «Админ» с паролем «111111» (только в пустую базу,
   чтобы не затронуть уже работающий портал);
3. поднимает uvicorn с ``app.main:app`` в фоновом потоке;
4. открывает страницу входа в браузере (кроме автозапуска и запуска
   установщиком);
5. остаётся в трее: меню из четырёх пунктов — «Открыть в браузере», адрес
   для входа с локальных ПК (щелчок копирует его), «Открыть папку с данными»
   и «Выход».

Автозапуск при входе в Windows включает установщик (флажок в его окне),
правило брандмауэра для входа с других компьютеров — запрос Windows при
первом запуске; в меню трея этих пунктов нет.

Журнал работы пишется в ``portal-desktop.log`` рядом с программой: в оконной
сборке у процесса нет консоли, поэтому stdout и stderr перенаправляются в файл.

Запуск с ключами:

* ``--autostart`` — старт из автозапуска Windows: браузер не открывается;
* ``--no-browser`` — не открывать браузер;
* ``--port 8010`` — порт сервера (по умолчанию ``PORTAL_PORT`` из ``.env`` или 8000);
* ``--create-admin`` — консольный режим создания администратора портала.
"""
import argparse
import asyncio
import ctypes
import importlib.util
import json
import logging
import logging.handlers
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Имя программы в системе: ярлыки, правило брандмауэра, ключ автозапуска
APP_TITLE = "Портал нотариальной конторы"
# Файл с портом работающего сервера: второй запуск открывает уже поднятый портал
STATE_FILE_NAME = "portal-desktop.json"
# Журнал настольного приложения
LOG_FILE_NAME = "portal-desktop.log"
# Порт по умолчанию и сколько следующих пробовать, если он занят
DEFAULT_PORT = 8000
PORT_ATTEMPTS = 20
# Имя объекта-мьютекса: не даёт открыть второй значок в том же сеансе Windows
MUTEX_NAME = "Local\\NotaryPortalDesktopTray"
# Учётная запись нотариуса, которая появляется при первом запуске установленного
# портала: пакет ставится «под ключ», пароль меняется в профиле сотрудника
DEFAULT_ADMIN_NAME = "Админ"
DEFAULT_ADMIN_PASSWORD = "111111"

logger = logging.getLogger("portal.desktop")

# Открытый файл журнала: держим ссылку, иначе поток закроется по сборке мусора
_log_stream = None


def app_dir() -> Path:
    """Папка программы: рядом с ``Portal.exe`` или корень проекта при запуске из кода."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def env_path() -> Path:
    """Путь к файлу настроек ``.env`` (приложение читает его из рабочей папки)."""
    return app_dir() / ".env"


def log_path() -> Path:
    """Путь к журналу настольного приложения."""
    return app_dir() / LOG_FILE_NAME


def state_path() -> Path:
    """Путь к файлу состояния с портом работающего сервера."""
    return app_dir() / STATE_FILE_NAME


def _attach_streams_to_log() -> None:
    """Перенаправляет stdout и stderr в журнал: в оконной сборке консоли нет."""
    global _log_stream
    if sys.stdout is not None and sys.stderr is not None:
        return
    _log_stream = log_path().open("a", encoding="utf-8", buffering=1)
    sys.stdout = _log_stream
    sys.stderr = _log_stream


def configure_logging() -> None:
    """Пишет журнал в файл с ротацией: 1 МБ на файл, 3 архивные копии."""
    handler = logging.handlers.RotatingFileHandler(
        log_path(), maxBytes=1_048_576, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)


def ensure_env_file() -> None:
    """Создаёт ``.env`` при первом запуске и заменяет в нём ключ-заглушку.

    Портал читает настройки из ``.env`` рядом с программой. В установочном
    пакете этого файла нет: его собирает эта функция, чтобы у каждой установки
    был свой ``SECRET_KEY`` (с общим ключом можно подделать cookie входа).
    """
    path = env_path()
    secret = secrets.token_hex(32)
    if not path.exists():
        path.write_text(
            "# Настройки портала. Файл создан при первом запуске.\n"
            "\n"
            "# Секрет для подписи JWT (сгенерирован автоматически)\n"
            f"SECRET_KEY={secret}\n"
            "\n"
            "# Строка подключения к БД (асинхронный драйвер)\n"
            "DATABASE_URL=sqlite+aiosqlite:///./portal.db\n"
            "\n"
            "# Время жизни access-токена в минутах\n"
            "ACCESS_TOKEN_EXPIRE_MINUTES=480\n"
            "\n"
            "# Папка резервных копий портала\n"
            "BACKUP_DIR=backups\n"
            "\n"
            "# Порт, на котором поднимается портал\n"
            f"PORTAL_PORT={DEFAULT_PORT}\n",
            encoding="utf-8",
        )
        logger.info("Создан файл настроек %s", path)
        return

    text = path.read_text(encoding="utf-8")
    if "replace-me-with-a-long-random-string" in text:
        path.write_text(
            text.replace("replace-me-with-a-long-random-string", secret),
            encoding="utf-8",
        )
        logger.info("В %s подставлен случайный SECRET_KEY", path)


async def _create_default_admin() -> bool:
    """Заводит нотариуса в пустой базе портала; ``True`` — запись создана."""
    from sqlalchemy import func, select

    from app.core.database import async_session_maker, engine
    from app.core.security import hash_password
    from app.db.base import Base
    from app.modules.auth import models as auth_models  # noqa: F401 — нужна таблица
    from app.modules.auth.models import User
    from app.modules.auth.schemas import name_key

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session_maker() as session:
            total = await session.scalar(select(func.count()).select_from(User))
            if total:
                return False
            session.add(
                User(
                    full_name=DEFAULT_ADMIN_NAME,
                    name_key=name_key(DEFAULT_ADMIN_NAME),
                    hashed_password=hash_password(DEFAULT_ADMIN_PASSWORD),
                    password_plain=DEFAULT_ADMIN_PASSWORD,
                    role="admin",
                )
            )
            await session.commit()
    finally:
        # Пул соединений освобождается: uvicorn поднимется в своём цикле событий
        await engine.dispose()
    return True


def seed_default_admin() -> None:
    """Создаёт учётную запись нотариуса при первом запуске портала.

    Установочный пакет ставится «под ключ»: сразу после установки вход открыт
    по имени «Админ» и паролю «111111» (регистр имени значения не имеет, пароль
    меняется в профиле). Запись добавляется только в пустую базу, поэтому
    сотрудники уже работающего портала не затрагиваются. Сбой на этом шаге
    не мешает запуску: администратора всегда можно создать пунктом трея.
    """
    if not getattr(sys, "frozen", False):
        return
    try:
        if asyncio.run(_create_default_admin()):
            logger.info(
                "Создана учётная запись нотариуса «%s» (пароль %s)",
                DEFAULT_ADMIN_NAME,
                DEFAULT_ADMIN_PASSWORD,
            )
    except Exception as exc:  # noqa: BLE001 — портал поднимается в любом случае
        logger.exception("Не удалось создать учётную запись нотариуса: %s", exc)


def _env_value(name: str) -> str | None:
    """Читает значение из переменных окружения или из ``.env`` (пары KEY=VALUE)."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        lines = env_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() == name:
            return value.strip()
    return None


def resolve_port(preferred: int | None = None) -> int:
    """Возвращает первый свободный порт: сначала запрошенный, затем следующие.

    Порт 8000 может быть занят другим сервером или второй копией портала —
    тогда портал поднимается на следующем свободном, а не падает с ошибкой.
    Порт считается занятым, если на него удаётся подключиться или если
    система не даёт его занять.
    """
    start = preferred or _port_from_env()
    for offset in range(PORT_ATTEMPTS):
        port = start + offset
        if port_is_open(port):
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("0.0.0.0", port))
            except OSError:
                continue
        if offset:
            logger.warning("Порт %s занят, портал поднимается на %s", start, port)
        return port
    raise RuntimeError(
        f"Не найден свободный порт в диапазоне {start}–{start + PORT_ATTEMPTS}"
    )


def _port_from_env() -> int:
    """Порт из ``PORTAL_PORT``; при ошибке в настройках — порт по умолчанию."""
    raw = _env_value("PORTAL_PORT")
    try:
        return int(raw) if raw else DEFAULT_PORT
    except ValueError:
        logger.warning("PORTAL_PORT=%s не число, беру %s", raw, DEFAULT_PORT)
        return DEFAULT_PORT


def portal_url(port: int) -> str:
    """Адрес страницы входа портала на этом компьютере."""
    return f"http://127.0.0.1:{port}/auth/login"


def lan_addresses() -> list[str]:
    """Адреса компьютера в локальной сети — для входа с других рабочих мест."""
    addresses: set[str] = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = item[4][0]
            if not address.startswith("127."):
                addresses.add(address)
    except OSError:
        pass
    return sorted(addresses)


def primary_lan_address() -> str | None:
    """Основной адрес компьютера в сети конторы (``None`` — сети нет).

    Система сообщает адрес того интерфейса, через который компьютер выходит
    в сеть, — именно его набирают на других рабочих местах. Виртуальные
    адаптеры (Hyper-V, VPN) при этом не попадают в меню первыми.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 53))
            address = probe.getsockname()[0]
    except OSError:
        address = ""
    if address and not address.startswith("127."):
        return address
    known = lan_addresses()
    return known[0] if known else None


def lan_portal_url(port: int) -> str | None:
    """Адрес портала для входа с других компьютеров (``None`` — сети нет)."""
    address = primary_lan_address()
    return f"http://{address}:{port}" if address else None


class SingleInstance:
    """Мьютекс Windows: второй запуск значка не создаёт, а открывает портал.

    Ярлык на рабочем столе и автозапуск могут сработать одновременно —
    вместо двух серверов на разных портах остаётся один значок в трее.
    """

    def __init__(self, name: str = MUTEX_NAME) -> None:
        self._name = name
        self._handle = None

    def acquire(self) -> bool:
        """Захватывает мьютекс; False — приложение уже запущено в этом сеансе."""
        try:
            kernel32 = ctypes.windll.kernel32
            self._handle = kernel32.CreateMutexW(None, False, self._name)
            # ERROR_ALREADY_EXISTS: мьютекс уже создан работающей копией
            return kernel32.GetLastError() != 183
        except (AttributeError, OSError):
            return True

    def release(self) -> None:
        """Освобождает мьютекс при выходе из приложения."""
        if self._handle:
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None


def write_state(port: int) -> None:
    """Запоминает порт работающего сервера для повторных запусков ярлыка."""
    try:
        state_path().write_text(json.dumps({"port": port}), encoding="utf-8")
    except OSError as exc:
        logger.warning("Не удалось записать %s: %s", state_path(), exc)


def read_state_port() -> int | None:
    """Порт уже работающего портала из файла состояния (если он есть)."""
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    port = data.get("port")
    return port if isinstance(port, int) else None


def port_is_open(port: int) -> bool:
    """Проверяет, что на порту этого компьютера кто-то принимает подключения."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def open_portal(port: int) -> None:
    """Открывает страницу входа портала в браузере по умолчанию."""
    webbrowser.open(portal_url(port))


class PortalServer:
    """Сервер портала в фоновом потоке.

    uvicorn занимает поток своим циклом событий, поэтому работает отдельно:
    главный поток нужен pystray для очереди сообщений значка в трее.
    """

    def __init__(self, port: int) -> None:
        self.port = port
        self._server = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Поднимает сервер и ждёт, пока он начнёт принимать подключения.

        Импорт ``app.main`` идёт после перехода в папку программы: приложение
        подключает шаблоны и статику относительными путями.
        """
        import uvicorn

        from app.main import app

        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=self.port,
            log_level="info",
            # Своё логирование uvicorn не настраивает: записи идут в корневой
            # регистратор, то есть в файл журнала рядом с программой
            log_config=None,
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, name="portal-uvicorn", daemon=True
        )
        self._thread.start()
        self.wait_ready()

    def wait_ready(self, timeout: float = 40.0) -> None:
        """Ждёт открытия порта; если сервер упал — понятная ошибка в журнале."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._thread is not None and not self._thread.is_alive():
                break
            if port_is_open(self.port):
                logger.info("Портал слушает http://127.0.0.1:%s", self.port)
                return
            time.sleep(0.2)
        raise RuntimeError(f"Сервер портала не поднялся на порту {self.port}")

    def stop(self) -> None:
        """Просит uvicorn завершиться и ждёт остановки потока."""
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)
        logger.info("Сервер портала остановлен")


def open_path(path: Path) -> None:
    """Открывает папку или файл в проводнике Windows."""
    os.startfile(str(path))  # noqa: S606 — так открывается проводник


def copy_to_clipboard(text: str) -> bool:
    """Кладёт текст в буфер обмена через ``clip.exe``: без сторонних пакетов.

    Адрес портала состоит из латиницы и цифр, поэтому кодировка консоли
    Windows здесь ничего не портит.
    """
    clip = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "clip.exe"
    if not clip.exists():
        return False
    try:
        subprocess.run(
            [str(clip)], input=text, text=True, check=True, timeout=10, shell=False
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def open_data_folder(icon=None, item=None) -> None:
    """Пункт меню трея: папка с базой, копиями и настройками портала."""
    open_path(app_dir())


def run_create_admin() -> int:
    """Консольный режим: скрипт проекта ``scripts/create_admin.py``.

    У оконной сборки консоли нет, поэтому она создаётся принудительно и
    стандартные потоки подключаются к ней — иначе вводить имя и пароль некуда.
    """
    ctypes.windll.kernel32.AllocConsole()
    sys.stdin = open("CONIN$", "r", encoding="utf-8", buffering=1)
    sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    sys.stderr = sys.stdout

    script = app_dir() / "scripts" / "create_admin.py"
    if not script.exists():
        print(f"Не найден скрипт создания администратора: {script}")
        return 1
    spec = importlib.util.spec_from_file_location("portal_create_admin", script)
    if spec is None or spec.loader is None:
        print("Не удалось загрузить скрипт создания администратора")
        return 1
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main())


def build_icon() -> "Image.Image":
    """Значок трея: файл ``logo.ico`` рядом с программой или простая заглушка."""
    from PIL import Image, ImageDraw

    for name in ("portal.ico", "logo.ico"):
        path = app_dir() / name
        if path.exists():
            try:
                return Image.open(path)
            except OSError as exc:
                logger.warning("Не удалось прочитать значок %s: %s", path, exc)
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 2, 62, 62), fill=(31, 61, 110, 255))
    draw.text((22, 18), "П", fill=(255, 255, 255, 255))
    return image


def create_tray_icon(port: int):
    """Значок в трее с меню из четырёх пунктов.

    «Открыть в браузере» — страница входа на этом компьютере; «Адрес
    подключения для локальных ПК» — строка с адресом, щелчок копирует его
    в буфер обмена (меню трея Windows не даёт выделить текст); «Открыть папку
    с данными» — база, резервные копии, настройки и журнал; «Выход» —
    останавливает сервер и убирает значок.
    """
    import pystray
    from pystray import Menu, MenuItem

    def reopen(icon=None, item=None) -> None:
        """Открывает страницу входа в браузере."""
        open_portal(port)

    def quit_app(icon=None, item=None) -> None:
        """Останавливает сервер и убирает значок."""
        logger.info("Выход из портала")
        if icon is not None:
            icon.stop()

    def copy_lan(icon=None, item=None, url: str = "") -> None:
        """Пункт меню трея: копирует адрес портала для другого компьютера."""
        copied = copy_to_clipboard(url)
        if icon is None:
            return
        try:
            icon.notify(
                f"Адрес скопирован: {url}" if copied else f"Адрес: {url}",
                APP_TITLE,
            )
        except Exception as exc:  # noqa: BLE001 — уведомление не обязательно
            logger.warning("Уведомление трея не показано: %s", exc)

    # Адрес в сети конторы: сотрудник набирает его на своём рабочем месте
    lan_url = lan_portal_url(port)
    if lan_url:
        lan_item = MenuItem(
            f"Адрес подключения для локальных ПК: {lan_url}",
            lambda icon, item: copy_lan(icon, item, lan_url),
        )
    else:
        # Сети нет — пункт остаётся на месте, но неактивен
        lan_item = MenuItem(
            "Адрес подключения для локальных ПК: сеть не найдена",
            None,
            enabled=False,
        )

    # Меню строго из четырёх пунктов; двойной щелчок по значку — открыть портал
    menu = Menu(
        MenuItem("Открыть в браузере", reopen, default=True),
        lan_item,
        MenuItem("Открыть папку с данными", open_data_folder),
        MenuItem("Выход", quit_app),
    )
    title = f"{APP_TITLE}\n{portal_url(port)}"
    if lan_url:
        title += f"\nС других ПК: {lan_url}"
    return pystray.Icon("notary-portal", build_icon(), title, menu)


def notify_error(message: str) -> None:
    """Показывает окно с ошибкой: без него оконное приложение молча не стартует."""
    ctypes.windll.user32.MessageBoxW(None, message, APP_TITLE, 0x10)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Разбирает ключи командной строки."""
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--autostart", action="store_true", help="запуск из автозапуска Windows")
    parser.add_argument("--no-browser", action="store_true", help="не открывать браузер")
    parser.add_argument("--port", type=int, default=None, help="порт сервера портала")
    parser.add_argument(
        "--create-admin", action="store_true", help="создать администратора портала"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Точка входа: поднимает сервер и держит значок в трее до команды «Выход»."""
    args = parse_args(argv)
    os.chdir(app_dir())
    _attach_streams_to_log()
    configure_logging()
    logger.info("Запуск портала из %s (ключи: %s)", app_dir(), sys.argv[1:])

    if args.create_admin:
        return run_create_admin()

    instance = SingleInstance()
    if not instance.acquire():
        # Портал уже запущен: просто открываем его страницу
        port = read_state_port()
        if port and port_is_open(port):
            logger.info("Портал уже работает на порту %s", port)
            open_portal(port)
            return 0
        notify_error("Портал уже запущен — значок находится в трее рядом с часами.")
        return 0

    try:
        ensure_env_file()
        seed_default_admin()
        port = resolve_port(args.port)
        server = PortalServer(port)
        server.start()
    except Exception as exc:  # noqa: BLE001 — показываем причину пользователю
        logger.exception("Портал не запустился")
        notify_error(
            f"Портал не запустился: {exc}\n\nПодробности в журнале:\n{log_path()}"
        )
        instance.release()
        return 1

    write_state(port)
    icon = create_tray_icon(port)
    if not args.no_browser and not args.autostart:
        # Браузер открываем после появления значка, чтобы окно не перекрыло трей
        threading.Timer(0.5, lambda: open_portal(port)).start()

    try:
        icon.run()
    finally:
        server.stop()
        state_path().unlink(missing_ok=True)
        instance.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
