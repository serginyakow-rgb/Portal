# Технический контекст

## Окружение разработки

- ОС Windows (`win32`), рабочий каталог `Portal/`, оболочка — PowerShell.
- Виртуальное окружение `venv/` в корне проекта (активируется в текущем
  терминале: приглашение `(venv)`).
- Файлы проекта в кодировке UTF-8; русские тексты. **Строки — CRLF**:
  при правках сохранять CRLF и UTF-8 без BOM (проверено для JS: счётчик CRLF
  равен числу строк, одиночных LF нет, BOM отсутствует).
- Сервер разработки обычно запущен на `http://127.0.0.1:8000`
  (`uvicorn app.main:app`), логи пишутся в `uvicorn.log` и `uvicorn.err`.

## Зависимости (`requirements.txt`, версии зафиксированы)

| Пакет | Версия |
| --- | --- |
| fastapi | 0.115.6 |
| uvicorn[standard] | 0.32.1 |
| SQLAlchemy | 2.0.36 |
| aiosqlite | 0.20.0 |
| alembic | 1.14.0 |
| Jinja2 | 3.1.4 |
| pydantic | 2.10.4 |
| pydantic-settings | 2.7.0 |
| python-multipart | 0.0.20 |
| passlib | 1.7.4 |
| bcrypt | 4.0.1 |
| python-jose[cryptography] | 3.3.0 |
| python-dotenv | 1.0.1 |

Новых зависимостей не добавлять: набор продуман и зафиксирован правилами
каркаса. Клиентский код — ванильный ES5-совместимый JS (`var`, IIFE), без
сборщиков и CDN.

## Конфигурация

`.env` (в git не попадает, есть `.env.example`):

| Переменная | Назначение | По умолчанию |
| --- | --- | --- |
| `SECRET_KEY` | подпись JWT | `dev-secret-change-me` |
| `DATABASE_URL` | подключение | `sqlite+aiosqlite:///./portal.db` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | жизнь токена | `480` |

## База данных

SQLite `portal.db` в корне (в `.gitignore`). Схему создаёт
`Base.metadata.create_all` в `lifespan` приложения — Alembic-миграций нет.
При изменении существующей схемы колонку добавляют вручную, например:
`ALTER TABLE users ADD COLUMN password_plain VARCHAR(128);` (описано в README).
Устаревшие примечания README о ручных ALTER могут не соответствовать текущему
коду — сверяться с `app/modules/*/models.py`.

## Как проверять изменения

Автотестов в проекте нет (нет `tests/`, pytest не в зависимостях). Рабочий
приём — одноразовые скрипты во временной папке
(`C:\Users\azaza\AppData\Local\Temp\`), которые не попадают в репозиторий:

- **Синтаксис JS**: `node --check app/static/js/<файл>.js`.
- **Клиентский расчёт**: Node-скрипт с DOM-заглушкой, подгружающий реальный
  `app/static/js/<файл>.js` через `vm`/`require` после подстановки
  `document`/`localStorage`; сценарий «ввёл значение → нажал `input` →
  прочитал `textContent` выходных полей». Образцы такого теста уже
  использовались для `calculators.js`, `udostoverenie-dkp.js`,
  `udostoverenie-dareniya.js`.
- **Страница целиком**: Python-скрипт без сторонних библиотек
  (`urllib.request`) с cookie `portal_token`, полученным из
  `app.core.security.create_access_token`, проверяющий код ответа, наличие
  `id` элементов, подписей и подключённых скриптов. БД читается через
  `sqlite3` (`portal.db`, `users.is_active = 1`) для получения `id` и `role`.
- **Проверка формулы в исходнике**: сравнение строк файла
  (`source.includes(...)`) — дешёвый способ убедиться, что старые константы
  удалены.

## Готовые скрипты проверок (лежат вне репозитория)

Одноразовые проверки, которыми подтверждались правки калькуляторов; лежат
во временной папке и в git не попадают — могут быть удалены системой, тогда их
проще написать заново по образцу:

| Скрипт | Что делает | Запуск |
| --- | --- | --- |
| `%TEMP%\test_kuplya_prodazha.js` | DOM-заглушка для `calculators.js`: 122 проверки сценариев и границ | `node %TEMP%\test_kuplya_prodazha.js app\static\js\calculators.js` |
| `%TEMP%\test_udostoverenie_dareniya.js` | то же для `udostoverenie-dareniya.js`: 74 проверки (границы 300 ₽ / 20 000 ₽, деление вдвое для родственников, стоимость доли) | `node %TEMP%\test_udostoverenie_dareniya.js app\static\js\udostoverenie-dareniya.js` |
| `%TEMP%\http_check_kuplya.py` | живой сервер: 29 проверок страницы, разметки, скриптов и соседних страниц | `python %TEMP%\http_check_kuplya.py` (отчёт — `%TEMP%\http_check_kuplya_out.txt`) |

Первый аргумент Node-тестов — путь к проверяемому скрипту; без него
`readFileSync(undefined)` падает с `ERR_INVALID_ARG_TYPE`.

Последний прогон (17.10.2026, после правки расчёта дарения): `node --check`
по всем шести скриптам — без ошибок; `test_kuplya_prodazha.js` — «проверок:
122, провалов: 0»; `test_udostoverenie_dareniya.js` — «проверок: 74,
провалов: 0»; `http_check_kuplya.py` — «проверок: 29, провалов: 0» (этот
прогон был до правки дарения). Дополнительно проверено на запущенном сервере:
`GET /static/js/udostoverenie-dareniya.js` → 200, в тексте есть `FEDERAL_MIN`,
`FEDERAL_MAX`, `FEDERAL_RATE`, `CLOSE_DIVISOR`, `federalBase`, старых
`*_COEFFICIENT` нет. Для HTTP-проверки сервер должен быть запущен
(`uvicorn app.main:app`, порт 8000); Cookie `portal_token` скрипт получает сам
через `create_access_token`.

## Состояние окружения на 17.10.2026

- Портал запущен для работы: `python -m uvicorn app.main:app --host 0.0.0.0
  --port 8000` из корня проекта (проверено 17.10.2026; процесс python, PID 7788,
  слушает `0.0.0.0:8000`; повторно подтверждено после правки дарения). Логи
  этого запуска — `%TEMP%\portal_uvicorn.log` и
  `%TEMP%\portal_uvicorn.err`: в `uvicorn.log`/`uvicorn.err` репозитория не
  пишем, потому что `uvicorn.err` отслеживается git и правка засоряет индекс.
- Вход: <http://127.0.0.1:8000/auth/login>; из локальной сети — по адресу
  машины (например, `http://192.168.1.71:8000/auth/login`), порт 8000 слушает
  все интерфейсы.
- Активен `venv` (Python 3.12.0); для `node --check` и DOM-тестов доступен
  Node.js v24.21.0.
- Ветка `main`, HEAD `d446500 First commit`, все правки раздела калькуляторов
  в индексе, не закоммичены; поверх — незастейдженная правка
  `app/static/js/udostoverenie-dareniya.js` (расчёт тарифа за дарение);
  `memory-bank/` — untracked.

## Известный мусор

- `app/static/_probe.html` — диагностическая страница (layout probe) для
  измерений вёрстки в iframe через хеш-параметры (`#url=…&rows=…&scroll=…`).
  Частью портала не является, роутов нет, но файл **отслеживается git**
  (попал в первый коммит). Кандидат на удаление, если больше не нужен.
- `uvicorn.err` в корне — баннер запуска uvicorn, файл **отслеживается git**
  (попал в первый коммит); соседний `uvicorn.log` игнорируется правилом
  `*.log`. Поэтому логи нового запуска пишем в `%TEMP%`: запись в
  `uvicorn.err` искажает индекс. Кандидат на удаление из репозитория.
