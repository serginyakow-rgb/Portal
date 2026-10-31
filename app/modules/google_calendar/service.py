"""Связь с Google Календарём: ключ OAuth-клиента, подключение и создание событий.

Библиотеки Google импортируются внутри функций: портал должен запускаться и без
них — раздел настроек тогда честно сообщает, что библиотеки не установлены.

Файлы ``credentials.json`` и ``token.json`` лежат в ``config/google_calendar``
и исключены из репозитория: это секреты.

Подключение выполняется на компьютере, где запущен портал. Google принимает
redirect_uri только для loopback-адресов (http://localhost, http://127.0.0.1),
а приватный IP вида 192.168.x.x отклоняет по политике secure response handling,
поэтому вход через браузер с другого компьютера сети технически невозможен.
Сохранённый токен общий: после одного подключения статус, проверка и создание
событий работают с любого компьютера локальной сети.
"""
import base64
import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import available_timezones

logger = logging.getLogger(__name__)

# Каталог секретов Google Календаря (исключён из git)
CONFIG_DIR = Path("config") / "google_calendar"
# Ключ OAuth-клиента: файл client_secret_*.json из Google Cloud Console
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"
# Токен доступа: создаётся после входа в Google, обновляется автоматически
TOKEN_PATH = CONFIG_DIR / "token.json"
# Адрес основного календаря (почта аккаунта) — для строки статуса
ACCOUNT_PATH = CONFIG_DIR / "account.txt"

# Права: просмотр и создание событий в календаре аккаунта
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Предел размера загружаемого ключа: файл client_secret_*.json занимает ~0.5 КБ
MAX_CREDENTIALS_SIZE = 64 * 1024

# Сколько портал ждёт подтверждения входа в браузере
CONNECT_TIMEOUT_SECONDS = 300

# Адреса, по которым Google разрешает вернуть код подтверждения
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

CALENDAR_API = "calendar"
CALENDAR_VERSION = "v3"

# Время события из карточки, если поле времени пустое (совпадает с формой)
DEFAULT_EVENT_TIME = "09:00"
# Сколько длится событие, созданное из карточки: столько идёт приём у нотариуса
EVENT_DURATION_MINUTES = 60


class GoogleCalendarError(RuntimeError):
    """Ошибка связи с календарём с текстом, который можно показать нотариусу."""


@dataclass(frozen=True)
class GoogleCalendarStatus:
    """Состояние связи с Google Календарём для страницы настроек."""

    # Установлены ли библиотеки google-api-python-client и google-auth-oauthlib
    libraries_installed: bool
    # Загружен ли файл ключа OAuth-клиента
    has_credentials: bool
    # Есть ли сохранённый токен (ещё не значит, что он рабочий)
    has_token: bool
    # Токен действителен или успешно обновлён
    connected: bool
    # Почта аккаунта, если её удалось определить при подключении
    account: str | None
    # Пояснение, почему связь не работает
    message: str | None


def libraries_available() -> bool:
    """Установлены ли библиотеки Google (портал работает и без них)."""
    try:
        import google_auth_oauthlib.flow  # noqa: F401
        import googleapiclient.discovery  # noqa: F401
    except ImportError:
        return False
    return True


def is_loopback_host(host: str | None) -> bool:
    """Открыт ли портал по адресу, на который Google вернёт код подтверждения."""
    return (host or "").strip().lower() in LOOPBACK_HOSTS


def save_credentials(raw: bytes) -> str | None:
    """Сохраняет ключ OAuth-клиента и сбрасывает прежний токен.

    Возвращает текст ошибки для нотариуса или ``None``, если ключ сохранён.
    """
    if not raw:
        return "Файл ключа не выбран"
    if len(raw) > MAX_CREDENTIALS_SIZE:
        return "Файл ключа слишком большой: ожидается JSON размером до 64 КБ"

    try:
        config = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "Файл не похож на JSON-ключ OAuth-клиента"

    if not isinstance(config, dict):
        return "Файл не похож на JSON-ключ OAuth-клиента"

    # Google кладёт параметры клиента в блок installed (Desktop) или web
    client = config.get("installed") or config.get("web")
    if not isinstance(client, dict):
        return "В файле нет блока installed или web — это не ключ OAuth-клиента Google"
    if not str(client.get("client_id") or "").strip():
        return "В ключе нет client_id: загрузите файл client_secret_*.json целиком"
    if not str(client.get("client_secret") or "").strip():
        return "В ключе нет client_secret: загрузите файл client_secret_*.json целиком"

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Пишем через временный файл, чтобы обрыв записи не испортил прежний ключ
    temporary = CREDENTIALS_PATH.with_name(CREDENTIALS_PATH.name + ".tmp")
    try:
        temporary.write_bytes(raw)
        temporary.replace(CREDENTIALS_PATH)
    except OSError as exc:
        logger.exception("Не удалось сохранить ключ OAuth-клиента Google Календаря")
        return f"Не удалось сохранить ключ в {CREDENTIALS_PATH}: {exc.strerror or exc}"

    # Токен от прежнего ключа недействителен — связь нужно выполнить заново
    _delete_token_files()
    _reset_connect_state()
    _clear_last_event()
    logger.info("Ключ OAuth-клиента Google Календаря сохранён в %s", CREDENTIALS_PATH)
    return None


def delete_credentials() -> None:
    """Удаляет ключ OAuth-клиента вместе с токеном: связь разрывается полностью."""
    for path in (CREDENTIALS_PATH, TOKEN_PATH, ACCOUNT_PATH):
        _unlink(path)
    _reset_connect_state()
    _clear_last_event()
    logger.info("Ключ OAuth-клиента Google Календаря удалён")


def disconnect() -> None:
    """Забывает токен доступа, оставляя загруженный ключ OAuth-клиента."""
    _delete_token_files()
    _reset_connect_state()
    _clear_last_event()
    logger.info("Токен Google Календаря удалён: подключение нужно выполнить заново")


def _delete_token_files() -> None:
    """Удаляет токен и запомненный адрес аккаунта."""
    for path in (TOKEN_PATH, ACCOUNT_PATH):
        _unlink(path)


def _unlink(path: Path) -> None:
    """Удаляет файл, если он есть (отсутствие файла — не ошибка)."""
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        logger.warning("Не удалось удалить файл %s", path, exc_info=True)


# Состояние фонового входа в Google: idle, pending, success или error.
# Страница настроек опрашивает его, пока нотариус подтверждает доступ в браузере.
_state_lock = threading.Lock()
_connect_state: dict[str, Any] = {
    "state": "idle",
    "message": None,
    "hint": None,
    "started_at": None,
}
# Последнее созданное тестовое событие — для ссылки на него в разделе настроек
_last_event: dict[str, str] | None = None


def connect_state() -> dict[str, Any]:
    """Копия состояния фонового входа в Google (безопасна для JSON-ответа)."""
    with _state_lock:
        return dict(_connect_state)


def last_test_event() -> dict[str, str] | None:
    """Последнее созданное тестовое событие или ``None``."""
    with _state_lock:
        return dict(_last_event) if _last_event else None


def _reset_connect_state() -> None:
    """Возвращает состояние входа в исходное положение."""
    with _state_lock:
        _connect_state.update(state="idle", message=None, hint=None, started_at=None)


def _clear_last_event() -> None:
    """Забывает ссылку на последнее тестовое событие."""
    global _last_event
    with _state_lock:
        _last_event = None


def get_status() -> GoogleCalendarStatus:
    """Текущее состояние связи для страницы настроек.

    Токен проверяется без обращения к Google, пока он действителен; при
    истечении срока он обновляется по refresh-токену.
    """
    installed = libraries_available()
    has_credentials = CREDENTIALS_PATH.is_file()
    has_token = TOKEN_PATH.is_file()

    connected = False
    message: str | None = None
    if has_token and installed:
        try:
            _load_credentials()
            connected = True
        except GoogleCalendarError as exc:
            message = str(exc)
        except Exception as exc:  # noqa: BLE001 - страница не должна падать из-за токена
            logger.exception("Не удалось проверить токен Google Календаря")
            message = f"Не удалось проверить сохранённый токен: {str(exc)[:200] or type(exc).__name__}"

    return GoogleCalendarStatus(
        libraries_installed=installed,
        has_credentials=has_credentials,
        has_token=has_token,
        connected=connected,
        account=_read_account(),
        message=message,
    )


def is_connected() -> bool:
    """Подключён ли календарь: в config/google_calendar есть сохранённый токен.

    Проверка намеренно без обращения к сети: её спрашивает каждая отрисовка
    доски задач (блок «Добавить в Google календарь» в форме карточки), а
    обновлять просроченный токен и объяснять причину отказа должен только
    раздел настроек — get_status().
    """
    return TOKEN_PATH.is_file()


def export_state(*, include_credentials: bool = False) -> dict[str, Any]:
    """Состояние связи для резервной копии: почта, флаги файлов и их содержимое.

    Без ``include_credentials`` в копию попадают только флаги — файл остаётся
    несекретным. С флагом кладётся содержимое ключа и токена в base64: такой
    файл нужно хранить как секрет, он даёт доступ к календарю аккаунта.
    """
    return {
        "account": _read_account(),
        "has_credentials": CREDENTIALS_PATH.is_file(),
        "has_token": TOKEN_PATH.is_file(),
        "credentials": _file_payload(CREDENTIALS_PATH) if include_credentials else None,
        "token": _file_payload(TOKEN_PATH) if include_credentials else None,
    }


def _file_payload(path: Path) -> dict[str, str] | None:
    """Файл в виде «имя + base64» для раздела копии; файла нет — None."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    return {"name": path.name, "content_base64": base64.b64encode(raw).decode("ascii")}


def _decode_payload(payload: Any, label: str) -> bytes | None:
    """Содержимое файла из копии: base64 → байты; файла в копии нет — None."""
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise GoogleCalendarError(
            f"В копии повреждён {label}: ожидался объект с содержимым файла"
        )
    content = payload.get("content_base64")
    if not isinstance(content, str) or not content:
        raise GoogleCalendarError(
            f"В копии повреждён {label}: нет содержимого файла"
        )
    try:
        return base64.b64decode(content, validate=True)
    except ValueError as exc:
        raise GoogleCalendarError(
            f"В копии повреждён {label}: содержимое не читается (base64)"
        ) from exc


def import_state(data: dict[str, Any], include_credentials: bool = True) -> None:
    """Возвращает файлы связи на место из раздела резервной копии.

    Сначала проверяются и декодируются все файлы из копии, и только потом
    что-либо пишется на диск: повреждённая копия не должна оставить портал
    с полузаписанным ключом. Файлы, которых в копии нет, не удаляются —
    восстановление старой копии без секретов не рвёт настроенную связь.
    """
    if not isinstance(data, dict):
        raise GoogleCalendarError("Раздел Google Календаря в копии повреждён")

    prepared: list[tuple[Path, bytes]] = []
    if include_credentials:
        for key, path, label in (
            ("credentials", CREDENTIALS_PATH, "ключ OAuth-клиента"),
            ("token", TOKEN_PATH, "токен доступа"),
        ):
            raw = _decode_payload(data.get(key), label)
            if raw is not None:
                prepared.append((path, raw))

    account = data.get("account")
    if account is not None and not isinstance(account, str):
        raise GoogleCalendarError(
            "В копии повреждён раздел Google Календаря: почта аккаунта"
        )

    if prepared or (isinstance(account, str) and account.strip()):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise GoogleCalendarError(
                f"Не удалось создать папку {CONFIG_DIR}: {exc.strerror or exc}"
            ) from exc

    for path, raw in prepared:
        try:
            path.write_bytes(raw)
        except OSError as exc:
            raise GoogleCalendarError(
                f"Не удалось записать файл {path.name}: {exc.strerror or exc}"
            ) from exc
        logger.info("Восстановлен файл Google Календаря: %s", path.name)

    if isinstance(account, str) and account.strip():
        try:
            ACCOUNT_PATH.write_text(account.strip(), encoding="utf-8")
        except OSError as exc:
            raise GoogleCalendarError(
                f"Не удалось записать файл {ACCOUNT_PATH.name}: {exc.strerror or exc}"
            ) from exc


def _read_account() -> str | None:
    """Почта аккаунта, определённая при подключении."""
    try:
        account = ACCOUNT_PATH.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return None
    return account or None


def _load_credentials():
    """Возвращает действующие учётные данные, обновляя токен при необходимости."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if not TOKEN_PATH.is_file():
        raise GoogleCalendarError(
            "Подключение к Google Календарю не выполнено: нажмите «Подключить» на компьютере с порталом"
        )

    try:
        credentials = Credentials.from_authorized_user_file(str(TOKEN_PATH), list(SCOPES))
        if not credentials.valid:
            if not credentials.refresh_token:
                raise GoogleCalendarError(
                    "Срок действия токена истёк — подключите календарь заново"
                )
            credentials.refresh(Request())
            _store_token(credentials, detect_account=False)
    except GoogleCalendarError:
        raise
    except RefreshError as exc:
        logger.warning("Google отклонил сохранённый токен: %s", exc)
        raise GoogleCalendarError(
            "Google отклонил сохранённый токен — подключите календарь заново"
        ) from exc
    except Exception as exc:  # noqa: BLE001 - повреждённый токен или нет связи
        logger.exception("Не удалось прочитать токен Google Календаря")
        raise GoogleCalendarError(
            f"Не удалось проверить сохранённый токен: {str(exc)[:200] or type(exc).__name__}"
        ) from exc

    return credentials


def _store_token(credentials, *, detect_account: bool = True) -> None:
    """Сохраняет токен доступа рядом с ключом OAuth-клиента."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")
    if not detect_account:
        return
    account = _fetch_primary_calendar_id(credentials)
    if account:
        try:
            ACCOUNT_PATH.write_text(account, encoding="utf-8")
        except OSError:
            logger.warning("Не удалось сохранить адрес аккаунта Google", exc_info=True)


def _fetch_primary_calendar_id(credentials) -> str | None:
    """Адрес основного календаря (почта аккаунта) — только для строки статуса."""
    try:
        service = _build_calendar_service(credentials)
        primary = service.calendars().get(calendarId="primary").execute()
    except Exception:  # noqa: BLE001 - адрес не критичен для подключения
        logger.warning("Не удалось определить адрес основного календаря", exc_info=True)
        return None
    return str(primary.get("id") or "").strip() or None


def _build_calendar_service(credentials):
    """Клиент Google Calendar API (импорт библиотеки — только при обращении)."""
    from googleapiclient.discovery import build

    return build(CALENDAR_API, CALENDAR_VERSION, credentials=credentials, cache_discovery=False)


@lru_cache(maxsize=1)
def _available_iana_timezones() -> frozenset[str]:
    """Имена часовых поясов IANA, известные библиотеке zoneinfo."""
    try:
        return frozenset(available_timezones())
    except Exception:  # noqa: BLE001 - без базы поясов работаем по смещению
        logger.debug("Список часовых поясов IANA недоступен", exc_info=True)
        return frozenset()


def _iana_timezone() -> str | None:
    """Имя часового пояса IANA, если оно известно.

    На Windows системное имя пояса не совпадает с IANA («RTZ 4 (зима)»),
    поэтому в событие передаётся только смещение в dateTime — Google его
    принимает, а неверный timeZone привёл бы к ошибке запроса.
    """
    name = os.environ.get("TZ", "").strip()
    if name and name in _available_iana_timezones():
        return name
    return None


def start_connect() -> str | None:
    """Запускает вход в Google в фоновом потоке.

    Возвращает текст ошибки для нотариуса или ``None``, если ожидание входа
    начато: браузер с разрешением доступа откроется на этом компьютере.
    """
    if not libraries_available():
        return "Не установлены библиотеки Google: выполните pip install -r requirements.txt и перезапустите портал"
    if not CREDENTIALS_PATH.is_file():
        return "Сначала загрузите файл ключа OAuth-клиента (client_secret_*.json)"

    with _state_lock:
        if _connect_state["state"] == "pending":
            return "Подключение уже выполняется: завершите вход в открывшемся окне браузера"
        _connect_state.update(
            state="pending",
            message=None,
            hint=None,
            started_at=datetime.now().isoformat(timespec="seconds"),
        )

    threading.Thread(
        target=_connect_worker,
        name="google-calendar-connect",
        daemon=True,
    ).start()
    return None


def _connect_worker() -> None:
    """Открывает браузер, ждёт подтверждение доступа и сохраняет токен."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
        credentials = flow.run_local_server(
            host="localhost",
            port=0,
            open_browser=True,
            timeout_seconds=CONNECT_TIMEOUT_SECONDS,
            authorization_prompt_message="Разрешите доступ к Календарю по ссылке: {url}",
            success_message="Готово: доступ к Google Календарю получен. Окно можно закрыть.",
        )
        _store_token(credentials)
    except Exception as exc:  # noqa: BLE001 - текст ошибки уходит в интерфейс
        logger.exception("Не удалось подключить Google Календарь")
        message = _connect_error_message(exc)
        with _state_lock:
            _connect_state.update(
                state="error", message=message, hint=_connect_error_hint(exc)
            )
        return

    logger.info("Google Календарь подключён, токен сохранён в %s", TOKEN_PATH)
    with _state_lock:
        _connect_state.update(
            state="success", message="Подключение выполнено", hint=None
        )


def _connect_error_message(exc: Exception) -> str:
    """Понятный нотариусу текст ошибки входа в Google."""
    text = str(exc)
    if type(exc).__name__ == "WSGITimeoutError":
        return "Время ожидания истекло: вход в Google не подтверждён. Нажмите «Подключить» ещё раз"
    if "access_denied" in text:
        return (
            "Google отклонил доступ (403 access_denied): аккаунт не входит в список "
            "тестовых пользователей приложения, приложение не прошло проверку "
            "или доступ заблокирован администратором домена"
        )
    if "redirect_uri_mismatch" in text:
        return "Google отклонил адрес возврата: подключение выполняется только на компьютере с порталом"
    return f"Не удалось подключиться к Google Календарю: {text[:200] or type(exc).__name__}"


def _connect_error_hint(exc: Exception) -> str | None:
    """Что проверить в Google Cloud Console при отказе во входе."""
    text = str(exc)
    if "access_denied" in text:
        return (
            "Проверьте в Google Cloud Console: 1) APIs & Services → OAuth consent screen → "
            "Publishing status = Testing, а аккаунт, под которым выполняется вход, добавлен "
            "в Test users; 2) Data access → добавлен scope "
            "https://www.googleapis.com/auth/calendar; 3) Library → Google Calendar API "
            "включён. Если аккаунт рабочий (Google Workspace), администратор домена должен "
            "разрешить это приложение."
        )
    if "redirect_uri_mismatch" in text:
        return (
            "Адрес возврата приходит на localhost компьютера с порталом. Откройте портал "
            "по адресу http://localhost:8000 и повторите подключение."
        )
    return None


def create_test_event(title: str = "Проверка связи с Google Календарём") -> dict[str, str]:
    """Создаёт событие на завтра в 10:00 и возвращает данные для ссылки.

    Проверка показывает нотариусу, что портал действительно пишет в календарь.
    """
    credentials = _load_credentials()
    start = _tomorrow_morning(hour=10)
    body = {
        "summary": title,
        "description": (
            "Событие создано порталом нотариальной конторы "
            "для проверки связи с Google Календарём."
        ),
        "start": _event_time(start),
        "end": _event_time(start + timedelta(minutes=30)),
    }

    try:
        service = _build_calendar_service(credentials)
        created = service.events().insert(calendarId="primary", body=body).execute()
    except Exception as exc:  # noqa: BLE001 - текст ошибки уходит в интерфейс
        logger.exception("Не удалось создать событие в Google Календаре")
        raise GoogleCalendarError(
            f"Google не принял событие: {str(exc)[:200] or type(exc).__name__}"
        ) from exc

    event = {
        "title": title,
        "start": start.strftime("%d.%m.%Y %H:%M"),
        "html_link": str(created.get("htmlLink") or ""),
    }
    global _last_event
    with _state_lock:
        _last_event = event
    logger.info("В Google Календаре создано тестовое событие: %s", event["html_link"])
    return event


def create_task_event(
    title: str,
    due_date: date,
    start_time: str = DEFAULT_EVENT_TIME,
    contact: str = "",
    description: str = "",
) -> dict[str, str]:
    """Создаёт в календаре событие из карточки задачи.

    Заголовок события — «Заголовок карточки», дата — «Срок», время — поле
    времени рядом с чекбоксом «Добавить в Google календарь» (пустое поле
    означает 09:00), описание — поля карточки «Контакт» и «Описание».
    Длительность — EVENT_DURATION_MINUTES: столько обычно длится приём.
    Дату в прошлом Google принимает, поэтому карточку можно завести задним
    числом — событие просто попадёт в прошедший день.

    Возвращает данные события для сообщения нотариусу. Если календарь
    не подключён или Google отказал, бросает GoogleCalendarError: карточка
    к этому моменту уже сохранена, и сбой календаря её не отменяет.
    """
    summary = (title or "").strip() or "Карточка портала"
    hour, minute = _parse_event_time(start_time)
    start = datetime(
        due_date.year, due_date.month, due_date.day, hour, minute
    ).astimezone()
    body = {
        "summary": summary,
        "description": _task_event_description(contact, description),
        "start": _event_time(start),
        "end": _event_time(start + timedelta(minutes=EVENT_DURATION_MINUTES)),
    }

    # Ошибка подключения (нет токена, истёк срок) уже содержит текст для экрана
    credentials = _load_credentials()

    try:
        service = _build_calendar_service(credentials)
        created = service.events().insert(calendarId="primary", body=body).execute()
    except Exception as exc:  # noqa: BLE001 - текст ошибки уходит в интерфейс
        logger.exception("Не удалось создать событие карточки в Google Календаре")
        raise GoogleCalendarError(
            f"Google не принял событие: {str(exc)[:200] or type(exc).__name__}"
        ) from exc

    event = {
        "title": summary,
        "start": start.strftime("%d.%m.%Y %H:%M"),
        "html_link": str(created.get("htmlLink") or ""),
    }
    logger.info("В Google Календаре создано событие карточки: %s", event["html_link"])
    return event


def _task_event_description(contact: str, description: str) -> str:
    """Описание события из полей карточки «Контакт» и «Описание».

    Пустые поля в текст не попадают: у карточки без контакта в событии
    не будет пустой строки «Контакт:».
    """
    parts: list[str] = []
    contact = (contact or "").strip()
    description = (description or "").strip()
    if contact:
        parts.append(f"Контакт: {contact}")
    if description:
        parts.append(description)
    return "\n\n".join(parts)


def _parse_event_time(value: str) -> tuple[int, int]:
    """Часы и минуты из поля времени; пустое или мусорное значение — 09:00."""
    try:
        moment = datetime.strptime((value or "").strip(), "%H:%M")
    except ValueError:
        moment = datetime.strptime(DEFAULT_EVENT_TIME, "%H:%M")
    return moment.hour, moment.minute


def _tomorrow_morning(hour: int) -> datetime:
    """Завтрашний день в указанный час по местному времени сервера."""
    tomorrow = datetime.now().astimezone() + timedelta(days=1)
    return tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)


def _event_time(moment: datetime) -> dict[str, str]:
    """Поле start/end события: RFC3339 со смещением и timeZone, если он известен."""
    payload = {"dateTime": moment.isoformat()}
    timezone = _iana_timezone()
    if timezone:
        payload["timeZone"] = timezone
    return payload
