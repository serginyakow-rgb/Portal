# Архитектурные паттерны

## Модуль = папка в `app/modules/`

Единый состав любого модуля:

```text
app/modules/<модуль>/
  models.py      модели SQLAlchemy (Mapped/mapped_column, Base из app.db.base)
  schemas.py     pydantic-схемы + справочники подписей *_LABELS
  service.py     бизнес-логика: функции запросов и расчётов
  routes.py      APIRouter без префикса — префикс задаётся в app/main.py
  dependencies.py (при необходимости) — зависимости FastAPI
```

- Роутеры подключаются в `app/main.py`: `auth` — без префикса,
  `calculators` — `prefix="/calculators"`, `templates_db` — `prefix="/templates-db"`.
- Модели импортируются в `main.py` до `Base.metadata.create_all`, иначе таблиц
  в БД не будет (`# noqa: F401`).
- Новые зависимости в `requirements.txt` не добавляются.

## Рендеринг страниц

- Все страницы идут через `render()` из `app/core/templating.py`: он
  докладывает `user`, `initials`, `role_label`, `role_labels`, `active_menu`.
- Шаблон наследует `app/templates/base.html`; рабочая область — `.workspace`,
  содержимое в `{% block content %}`, скрипты — в `{% block scripts %}`.
- `active_menu` — строковый ключ пункта меню (`panel`, `templates_db`,
  `calculators`, `users`, `profile`); константы `MENU_*` объявляются
  в `app/core/templating.py` (общие) или в роутере модуля (разделовые).
- Ошибки валидации формы: `ValidationError` → первый текст через
  `_validation_message()` → та же страница с `error` и кодом 400.
  Успех — `RedirectResponse` со статусом 303 и флагом в query
  (`?saved=1`, `?updated=1`, `?deleted=1`).
- Доступ: `CurrentUser` (любой авторизованный) и
  `Annotated[User, Depends(require_role("admin"))]` для админ-разделов.

## Два способа расчёта в калькуляторах

- **Клиентский** (по умолчанию): расчёт в `app/static/js/<slug>.js`, показатели
  обновляются при вводе, значения полей живут в `localStorage`.
- **Серверный**: форма `POST` на тот же адрес, считает `service.py`, ответ —
  та же страница с результатом (образец — госпошлина).

## Клиентский скрипт блока (образец — `calculators.js`)

- Весь код в IIFE, ES5 (`var`, `function`), без сборщиков и CDN.
- Сверху файла — константы: `STORAGE_*` (ключи localStorage) и расчётные
  константы/тексты ошибок; ниже — блок `var el = document.getElementById(...)`
  для всех полей; если форма на странице отсутствует, скрипт выходит молча
  (`if (!form) { return; }`) — один файл можно безопасно подключать шире.
- Чтение чисел: `readNumber(input)` — «1 000 000,50» → число, мусор и пустая
  строка → 0 (не `NaN`).
- Формат вывода: `formatMoney(value)` — целые рубли, неразрывный пробел между
  разрядами и перед «₽» (`250000` → `250 000 ₽`); функция `render(el, value)`
  пишет значение в `textContent`.
- Разбор доли: `readShare(raw)` → `{ filled, valid, numerator, denominator }`;
  недействительны знаменатель 0, числитель больше знаменателя, нечисловой ввод.
- Сохранение: `saveValue()`/`restoreValue()`/`storageGet()`/`storageRemove()`;
  при загрузке страницы значения восстанавливаются, затем вызывается расчёт.
- Скрытые/некорректные поля не должны давать `NaN` в показателях: пустая цена
  даёт 0 (тарифа нет), некорректная доля — льгота 0 и сообщение об ошибке.
- Форма ничего не отправляет: `submit` перехватывается и отменяется.
- Общий формат сумм в полях ввода — `app/static/js/money-input.js`
  (не дублировать разметку/маску в блоках).
- Округление денег: считать «до округления», показывать `Math.round(...)`
  (в калькуляторах — рубль без копеек).

## Дизайн

- Утверждённый дизайн-код — `styles.css` в корне проекта; его рабочая копия
  `app/static/css/styles.css` подключается шаблонами (`base.html`), правки
  раздела вносятся только в неё (правило `clinerules/02-calculators.md`).
- Факт на 17.10.2026: правка `.calc__out` (`justify-content: center` →
  `flex-start`) сделана в **обеих** копиях, чтобы файлы не расходились. Это
  расходится с правилом «корневой `styles.css` не менять» — открытый вопрос
  в `activeContext.md` (откатить корень или разрешить синхронизацию).
- Токены: `--navy #0A2A4D`, `--gold #D4AF37`, `--bg #FAFAFA`,
  `--surface #FFFFFF`, `--text #333333`, `--muted #6B7280`,
  `--divider #E0E0E0`, `--warning #F0785A`, `--success #10B981`,
  `--radius 6px`, шрифты `--font` (Segoe UI) и `--font-brand` (Georgia).
- Классы-каркасы: `.panel`, `.panel__head`, `.panel__title`, `.panel__hint`,
  `.field`, `.calc__form`, `.calc__row`, `.btn.btn--primary`, `.table`,
  `.table-wrap`, `.card`, `.status--done`, `.status--warn`.

## Стиль кода и текстов

- Комментарии, docstring и тексты интерфейса — на русском, поясняют «почему»,
  а не «что». Docstring у модулей, функций и классов.
- Имена в Python — `snake_case`, в JS — `camelCase`, классы CSS — БЭМ-подобные
  (`.block__element--modifier`).
- Файлы UTF-8, строки CRLF.
- Правки в существующем коде — минимальные и в его стиле; новый модуль не
  требует переписывания соседних.

## Правила проекта

`clinerules/01-carcass.md` (каркас, стек, структура, запреты) и
`clinerules/02-calculators.md` (раздел «Калькуляторы»: порядок частей страницы,
разметка, эталонный код блока) — обязательны к соблюдению. `memory-bank/`
их не заменяет: это справочник состояния, а не правила.
