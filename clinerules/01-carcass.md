РОЛЬ
Ты — senior Python-разработчик. Ты не создаёшь проект с нуля каждый раз, а
расширяешь существующий каркас по чётким правилам. Никакой самодеятельности:
только то, что описано ниже.

============================================================
ЦЕЛЬ ЗАДАЧИ
============================================================
Создать ПЕРВИЧНЫЙ КАРКАС внутреннего портала нотариальной конторы,
работающего в локальной сети (до 15 пользователей).
Каркас должен быть расширяемым: дальнейшие модули (карточки-заготовки,
калькуляторы, канбан, Google Calendar) будут добавляться как отдельные
папки-модули БЕЗ переписывания существующего кода.

============================================================
ТЕХНОЛОГИЧЕСКИЙ СТЕК (СТРОГО)
============================================================
- Python 3.11+
- FastAPI (ASGI-сервер: uvicorn)
- SQLAlchemy 2.0 (ORM, async-движок)
- SQLite (файл portal.db в корне; позже заменим на PostgreSQL)
- Jinja2 (шаблоны HTML, рендеринг на сервере)
- Alembic (миграции, но в этой задаче только инициализация конфигурации)
- passlib[bcrypt] + python-jose[cryptography] для хеширования и JWT
- python-dotenv для конфигурации (.env)
- Никаких React/Vue/Node на этом этапе. Только серверный рендеринг.

============================================================
СТРУКТУРА ПРОЕКТА (СОЗДАТЬ ИМЕННО ТАК)
============================================================
notary_portal/
│
├── .env                       # SECRET_KEY, DATABASE_URL, ACCESS_TOKEN_EXPIRE_MINUTES
├── .env.example               # то же, но с плейсхолдерами
├── .gitignore                 # venv/, __pycache__/, *.db, .env
├── requirements.txt           # все зависимости с фиксированными версиями
├── README.md                  # как запустить: uvicorn app.main:app --reload
├── alembic.ini                # конфиг Alembic
│
├── app/
│   ├── __init__.py
│   ├── main.py                # точка входа FastAPI, подключение роутеров и статики
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py          # класс Settings (pydantic-settings), чтение .env
│   │   ├── security.py        # hash_password, verify_password, create_access_token
│   │   └── database.py        # async engine, async_session_maker, get_db()
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   └── base.py            # DeclarativeBase (Base) — единый для ВСЕХ моделей
│   │
│   ├── modules/               # ← СЮДА добавляются ВСЕ будущие функции
│   │   ├── __init__.py
│   │   │
│   │   └── auth/              # модуль аутентификации (первый)
│   │       ├── __init__.py
│   │       ├── models.py      # User (id, email, full_name, hashed_password,
│   │       │                  #       role, is_active, created_at)
│   │       ├── schemas.py     # Pydantic: UserCreate, UserRead, Token
│   │       ├── service.py     # бизнес-логика: create_user, authenticate_user
│   │       ├── dependencies.py# get_current_user, require_role(...)
│   │       └── routes.py      # APIRouter: /login, /logout, /register(admin-only)
│   │
│   ├── templates/
│   │   ├── base.html          # общий каркас: <head>, header, sidebar, {% block content %}
│   │   ├── auth/
│   │   │   └── login.html     # страница входа (стилизация — см. ниже)
│   │   └── dashboard/
│   │       └── index.html     # заглушка главной страницы с примером карточек
│   │
│   └── static/
│       ├── css/
│       │   └── styles.css     # ← СКОПИРОВАТЬ приложенный styles.css БЕЗ ИЗМЕНЕНИЙ
│       └── js/
│           └── app.js         # пустой файл-заготовка (пока без логики)
│
└── scripts/
    └── create_admin.py        # CLI: создать первого пользователя-админа
============================================================
ТРЕБОВАНИЯ К КОДУ
============================================================

Все роуты — async def. Все обращения к БД — через async session.

Модели SQLAlchemy наследуются ТОЛЬКО от Base из app/db/base.py.

Каждый модуль в app/modules/ самодостаточен: свои models, schemas,
service, routes. Роутер модуля подключается в app/main.py одной строкой:
from app.modules.auth.routes import router as auth_router
app.include_router(auth_router, prefix="/auth", tags=["auth"])

Никаких SQL-строк вручную — только SQLAlchemy ORM.

Пароли — только bcrypt-хеши. JWT в HttpOnly cookie (не в localStorage).

Валидация входных данных — через Pydantic-схемы, не вручную.

Комментарии на русском, кратко и по делу. Без «TODO: fix later».

Никаких глобальных переменных-синглтонов, кроме engine/session_maker.

requirements.txt — с точными версиями (==), совместимыми между собой.

Не создавай файлы, которых нет в структуре выше. Не удаляй существующие.

============================================================
ИНТЕГРАЦИЯ СО styles.css (КРИТИЧНО)
============================================================
В корне проекта лежит файл styles.css — это УТВЕРЖДЁННЫЙ дизайн-код портала.
Его НЕЛЬЗЯ менять, переписывать или «улучшать».

Действия:

Скопируй styles.css в app/static/css/styles.css БЕЗ единого изменения.

В app/templates/base.html подключи его так:

<link rel="stylesheet" href="{{ url_for('static', path='css/styles.css') }}">
HTML-разметка шаблонов ОБЯЗАНА использовать ТОЛЬКО классы из styles.css.
Никаких inline-style, никаких собственных CSS-файлов, никакого Tailwind.
Доступные классы (используй их буквально):
.app, .header, .header__brand, .brand__mark, .brand__text,
.brand__title, .brand__sub, .header__actions, .icon-btn,
.icon-btn__badge, .profile, .profile__ava, .profile__meta,
.profile__name, .profile__role,
.layout, .sidebar, .sidebar__label, .menu, .menu__item,
.menu__text, .menu__count, .sidebar__footer, .dot-live,
.workspace, .panel, .panel__head, .panel__title, .panel__hint,
.cards, .card, .card__marker, .card__title, .card__meta,
.card__foot, .status, .status--done, .status--warn, .status--progress,
.table-wrap, .table, .mono,
.btn, .btn--primary, .btn--ghost,
.calc, .calc__form, .field, .calc__out, .calc__row,
.chat, .chat__header, .chat__title, .chat__messages,
.msg, .msg--me, .msg--system, .msg__ava, .msg__body, .msg__head,
.msg__author, .msg__bubble, .chat__day, .composer

Иконки — inline SVG (Lucide-стиль, stroke="currentColor", width/height 20-21).
Не подключай внешние библиотеки иконок.

Шрифты — системные (Segoe UI, Georgia) — уже заданы в CSS, ничего не добавляй.

============================================================
ЧТО ИМЕННО СДЕЛАТЬ В ЭТОЙ ЗАДАЧЕ (ПОШАГОВО)
============================================================
Шаг 1. Создай дерево каталогов и все init.py (пустые).
Шаг 2. Напиши app/core/config.py — Settings через pydantic-settings,
читает .env (SECRET_KEY, DATABASE_URL, ACCESS_TOKEN_EXPIRE_MINUTES=480).
Шаг 3. Напиши app/core/database.py — async engine + async_session_maker + get_db().
Шаг 4. Напиши app/db/base.py — class Base(DeclarativeBase): pass.
Шаг 5. Напиши app/modules/auth/models.py — модель User (см. поля выше).
Шаг 6. Напиши app/modules/auth/schemas.py — Pydantic-схемы.
Шаг 7. Напиши app/core/security.py — bcrypt + JWT (HS256).
Шаг 8. Напиши app/modules/auth/service.py — create_user, authenticate_user.
Шаг 9. Напиши app/modules/auth/dependencies.py — get_current_user (читает
JWT из cookie), require_role("admin").
Шаг 10. Напиши app/modules/auth/routes.py — GET /login (форма),
POST /login (установка cookie + redirect на /), GET /logout,
POST /register (только для роли admin).
Шаг 11. Напиши app/templates/base.html — используя классы .app, .header,
.layout, .sidebar, .menu, .workspace. Меню слева: пункты
«Панель», «Лица», «Карточки», «Калькуляторы», «Канбан», «Календарь»
(пока неактивные, кроме «Панель» — ведут на "#").
Правый верх: .icon-btn с колокольчиком и .profile с инициалами
текущего пользователя.
Шаг 12. Напиши app/templates/auth/login.html — наследует base.html,
форма внутри .panel с двумя .field (email, password) и
кнопкой .btn.btn--primary.
Шаг 13. Напиши app/templates/dashboard/index.html — заглушка: .panel
с заголовком «Панель» и 3-4 карточки .card с примерами дел
(номер, название, статус .status--done / .status--warn).
Шаг 14. Напиши app/main.py — FastAPI, монтирование /static, подключение
auth-роутера, редирект с / на /dashboard, обработка 401 → /auth/login.
Шаг 15. Напиши scripts/create_admin.py — создаёт первого админа
(email и пароль спрашивает через input()).
Шаг 16. Напиши requirements.txt, .env.example, .gitignore, README.md,
alembic.ini (без миграций, только конфиг).
Шаг 17. Скопируй приложенный styles.css в app/static/css/styles.css.
Шаг 18. Создай пустой app/static/js/app.js.

============================================================
ЧЕГО НЕ ДЕЛАТЬ
============================================================

Не менять styles.css.

Не добавлять CSS-фреймворки, иконочные шрифты, CDN-ссылки.

Не создавать модули cards/calculators/kanban/calendar — они будут позже
отдельными задачами.

Не писать миграции Alembic в этой задаче.

Не добавлять Docker, nginx, CI/CD — это отдельные этапы.

Не использовать синхронный SQLAlchemy.

Не хранить JWT в localStorage.

Не создавать «на будущее» пустые абстракции и базовые репозитории.

============================================================
ФОРМАТ ОТВЕТА
============================================================

Сначала выведи дерево создаваемых файлов (кратко, без содержимого).

Затем по одному файлу: путь + полный код в блоке python /html / ```text.

В конце — команды для запуска:
python -m venv venv
source venv/bin/activate # или venv\Scripts\activate на Windows
pip install -r requirements.txt
python scripts/create_admin.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Не задавай уточняющих вопросов — все решения уже приняты выше.

Если чего-то не хватает — выбери разумный дефолт и продолжай.

