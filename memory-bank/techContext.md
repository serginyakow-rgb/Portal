# Технический контекст

## Окружение разработки

- ОС Windows (`win32`), рабочий каталог `Portal/`, оболочка — PowerShell.
- Виртуальное окружение `venv/` в корне проекта (активируется в текущем
  терминале: приглашение `(venv)`).
- Файлы проекта в кодировке UTF-8; русские тексты. **Строки — CRLF**:
  при правках сохранять CRLF и UTF-8 без BOM (проверено для JS: счётчик CRLF
  равен числу строк, одиночных LF нет, BOM отсутствует).
- Сервер разработки обычно запущен на `http://127.0.0.1:8000`
  (`uvicorn app.main:app`). `run.bat` выводит лог в консоль; при ручных
  запусках логи пишем в `%TEMP%` — файлы `uvicorn.log`/`uvicorn.err` в корне
  остались от прежних запусков, причём `uvicorn.err` отслеживается git.

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
- **Вёрстка без сервера**: локальный HTML-снимок нужной разметки с
  `<link rel="stylesheet" href="file:///…/app/static/css/styles.css">`,
  открыть в headless Chrome и вывести метрики через
  `getComputedStyle(el, "::after")` (`content`, `fontSize`, `color`,
  `paddingRight`) и `getBoundingClientRect()`. Так проверялся знак «₽»:
  авторизация и запущенный сервер не нужны, стили берутся из рабочей копии.

## Готовые скрипты проверок (лежат вне репозитория)

Одноразовые проверки калькуляторов и раздела «Задачи»; лежат
во временной папке и в git не попадают — могут быть удалены системой, тогда их
проще написать заново по образцу:

| Скрипт | Что делает | Запуск |
| --- | --- | --- |
| `%TEMP%\test_kuplya_prodazha.js` | DOM-заглушка для `calculators.js`: 122 проверки сценариев и границ | `node %TEMP%\test_kuplya_prodazha.js app\static\js\calculators.js` |
| `%TEMP%\test_udostoverenie_dareniya.js` | то же для `udostoverenie-dareniya.js`: 74 проверки (границы 300 ₽ / 20 000 ₽, деление вдвое для родственников, стоимость доли) | `node %TEMP%\test_udostoverenie_dareniya.js app\static\js\udostoverenie-dareniya.js` |
| `%TEMP%\http_check_kuplya.py` | живой сервер: 29 проверок страницы, разметки, скриптов и соседних страниц | `python %TEMP%\http_check_kuplya.py` (отчёт — `%TEMP%\http_check_kuplya_out.txt`) |
| `%TEMP%\http_check_dareniya.py` | живой сервер: 41 проверка страницы дарения — разметка, поля, порядок расчёта, отсутствие лишней подписи карточки | `python %TEMP%\http_check_dareniya.py` (отчёт — `%TEMP%\http_check_dareniya_out.txt`) |
| `%TEMP%\css_http_check.py` | живой сервер: 25 проверок CSS и страниц — `.calc__out` без вертикального центрирования, `flex-start`, сохранённые padding/gap и горизонтальное выравнивание | `python %TEMP%\css_http_check.py` (отчёт — `%TEMP%\css_http_check_out.txt`) |
| `%TEMP%\make_calc_probe.py` | сохраняет четыре страницы калькуляторов с измерительным скриптом в `%TEMP%\calc_<имя>.html` для проверки вёрстки в браузере | `python %TEMP%\make_calc_probe.py`, затем headless Chrome |

Проверки доски «Задачи» (25.10.2026) шли скриптом
`%TEMP%\check_tasks_done_sort.py` — 28 живых HTTP-проверок: подсветка срока
снята только в столбце `done`, порядок столбца после переноса совпадает
с `list_board`, `data-task-due` есть в разметке, чужой id даёт `404`.
Нужен временный uvicorn на `127.0.0.1:8011` и копия базы
`%TEMP%\portal_check.db`. После прогона скрипт удалён; при повторе он
собирается по тому же образцу (Cookie `portal_token` — через
`create_access_token`, запросы — `urllib` к `:8011`).

Первый аргумент Node-тестов — путь к проверяемому скрипту; без него
`readFileSync(undefined)` падает с `ERR_INVALID_ARG_TYPE`.

Последний прогон (17.10.2026, после правки расчёта дарения и выравнивания
`.calc__out`): `node --check` по всем шести скриптам — без ошибок;
`test_kuplya_prodazha.js` — «проверок: 122, провалов: 0»;
`test_udostoverenie_dareniya.js` — «проверок: 74, провалов: 0»;
`http_check_dareniya.py` — «проверок: 41, провалов: 0»;
`http_check_kuplya.py` — «проверок: 29, провалов: 0»;
`css_http_check.py` — «проверок: 25, провалов: 0» (сервер отдаёт `.calc__out`
с `justify-content: flex-start`, вертикального центрирования не осталось).
Проверено на запущенном сервере: `GET /static/js/udostoverenie-dareniya.js`
→ 200, в тексте есть `FEDERAL_MIN`, `FEDERAL_MAX`, `FEDERAL_RATE`,
`CLOSE_DIVISOR`, `federalBase`, старых `*_COEFFICIENT` нет. Для HTTP-проверки
сервер должен быть запущен (`uvicorn app.main:app`, порт 8000); Cookie
`portal_token` скрипт получает сам через `create_access_token`.

### Проверка вёрстки в реальном браузере

Скрипт `%TEMP%\make_calc_probe.py` сохраняет четыре страницы раздела
(`/calculators/udostoverenie-dareniya`, `/calculators/udostoverenie-dkp`,
`/calculators/kuplya-prodazha`, `/calculators/gosposhlina`) вместе с их
стилями; страницы открываются в headless Chrome (`--headless=new
--window-size=1600,1200 --dump-dom`) и измеряются через
`getBoundingClientRect()`: сравниваются `top` подписи первого показателя
`.calc__out .label` и подписи первого поля `.calc__form .label`. Результат
17.10.2026 — разница **0.00 px** на всех четырёх страницах,
`getComputedStyle(.calc__out).justifyContent` = `flex-start`. Браузер:
`C:\Program Files\Google\Chrome\Application\chrome.exe` (единственная
установленная копия; x86 и пользовательская отсутствуют).

Проверка вёрстки «Расчет и сдача» (17.10.2026) тем же способом: страница
сохранена из авторизованной сессии в `%TEMP%\calc_probe.html`, в `<head>`
добавлен `<base href="http://127.0.0.1:8011/">`, чтобы стили и скрипты
подгружались с сервера; измерения `getBoundingClientRect()` дали два столбца
340/340, 15 полей 303×44, «Итого» 302×44, шаг строк 52;
`document.documentElement.scrollWidth` = `clientWidth` (горизонтальной
прокрутки нет). Это замер первой версии — из 15 полей и одного «Итого».

После сокращения до 12 полей и появления трёх полей вывода знак «₽» проверен
без сервера: снимок правого столбца с `<link>` на рабочую копию
`app/static/css/styles.css`, headless Chrome, метрики `::after` — `content`
«₽», 28px, «Итого» `rgb(240, 120, 90)` (= `--warning`), остальные
`rgb(51, 51, 51)` (= `--text`), `padding-right` поля 34px, высота поля 59px.
Первый прогон показал дефект (input уезжал в третью строку сетки, знак
оказывался над полем) — исправлен `grid-area: 2 / 1` у input.

## Состояние окружения на 25.10.2026

- Портал сейчас **не запущен**: 25.10.2026 `GET http://127.0.0.1:8000/auth/login`
  ответа не даёт (соединение отклонено). Запуск при необходимости —
  `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` из корня проекта;
  вход <http://127.0.0.1:8000/auth/login>, из локальной сети — по адресу
  машины (например, `http://192.168.1.71:8000/auth/login`). Логи пишем
  в `%TEMP%` (`portal_uvicorn.log` / `portal_uvicorn.err`), а не в файлы
  репозитория.
- Проверки правок доски «Задачи» (25.10.2026) шли на отдельном временном
  сервере `127.0.0.1:8011` с копией базы `%TEMP%\portal_check.db`: рабочий
  порт 8000 не занимали, настоящий `portal.db` не трогали. После прогона
  (28/28) временный процесс остановлен.
- Активен `venv` (Python 3.12.0); для `node --check` и DOM-тестов доступен
  Node.js v24.21.0. Браузер для проверок вёрстки —
  `C:\Program Files\Google\Chrome\Application\chrome.exe`.
- Git: HEAD — `18dfb0f` («Задачи: форма карточки, описание, Google Календарь
  и правка щелчком»), ветка `main` (30 коммитов) и `origin/main` совпадают.
  В индексе 104 файла; `memory-bank/` отслеживается git с коммита `d62e656`.
  Поверх HEAD в рабочем дереве лежат 12 незакоммиченных файлов (8 кодовых
  и 4 документальных) — правки доски «Задачи» (срок в «Готово», сортировка
  столбца, тип «Личное», подпись «Тип задачи») и обновление документации;
  подробности — `activeContext.md`, раздел «Состояние репозитория».
- Отправка выполнена через Git Credential Manager (helper `manager`), логин
  `serginyakow-rgb`; force-push не использовался, история линейная.

## Известный мусор

- `app/static/_probe.html` — диагностическая страница (layout probe) для
  измерений вёрстки в iframe через хеш-параметры (`#url=…&rows=…&scroll=…`).
  Частью портала не является, роутов нет. Выведена из git коммитом `936e469`
  и удалена с диска; правило `app/static/_probe.html` в `.gitignore` осталось,
  чтобы файл не вернулся в индекс.
- `uvicorn.err` и `uvicorn.log` в корне — вывод ручных запусков сервера.
  В индексе их нет (выведены коммитом `936e469`), `.gitignore` содержит
  `*.log` и `*.err`; на диске файлы остаются и правкам не мешают. Логи
  проверочных запусков пишем в `%TEMP%`.
- Прежние логи и скрипты проверок (`%TEMP%\portal_uvicorn.*`,
  `%TEMP%\calc_server.*`, `%TEMP%\check_tasks_done_sort.py`) — вне
  репозитория, их можно удалять в любой момент.
