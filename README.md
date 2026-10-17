# Портал нотариальной конторы

Внутренний портал конторы: FastAPI + SQLAlchemy 2.0 (async) + Jinja2 + SQLite.
Вход в портал выполняется по **имени сотрудника на русском языке и паролю**.

## Стек

- FastAPI 0.115, Uvicorn
- SQLAlchemy 2.0 (async) + aiosqlite
- Jinja2 (шаблоны), passlib/bcrypt (пароли), python-jose (JWT HS256)

## Структура

```text
app/
  core/       config.py, database.py, security.py, templating.py
  db/         base.py (единый DeclarativeBase)
  modules/    auth/ (models, schemas, service, dependencies, routes)
  templates/  base.html, auth/, dashboard/
  static/     css/styles.css, js/app.js
scripts/      create_admin.py
clinerules/   01-carcass.md — правила проекта
```

Подробная карта проекта — [`PROJECT_MAP.md`](PROJECT_MAP.md): схема слоёв,
маршруты, модели данных, связки шаблонов и JavaScript, сценарии работы.

## Быстрый старт

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # и подставить свой SECRET_KEY
python scripts/create_admin.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Портал: <http://127.0.0.1:8000/auth/login>

## Вход и роли

- Логин — имя сотрудника: только русские буквы, пробел и дефис (например, `Иванов Иван Иванович`).
- Пароль проверяется по bcrypt-хешу; JWT лежит в httpOnly-cookie `portal_token`.
- В токене хранится только `id` пользователя, поэтому смена имени и пароля не разрывает активную сессию.
- Рядом с хешем пароль хранится в открытом виде (`password_plain`): администратор видит его в разделе «Пользователи» и может выдать сотруднику заново.
- Неавторизованный запрос (401) ведёт на `/auth/login`, запрос без прав (403) — на `/dashboard?denied=1`.

| Раздел | Маршрут | Доступ |
| --- | --- | --- |
| Вход | `GET/POST /auth/login` | все |
| Выход | `POST /auth/logout` | авторизованные |
| Панель | `GET /dashboard` | авторизованные |
| Пользователи: список, добавление, форма правки | `GET /auth/users` (`?edit=<id>` — форма правки) | только `admin` |
| Добавление сотрудника | `POST /auth/register` | только `admin` |
| Изменение имени и пароля сотрудника | `POST /auth/users/{id}/update` | только `admin` |
| Удаление сотрудника | `POST /auth/users/{id}/delete` | только `admin` (кроме себя) |
| Свой профиль | `GET /auth/profile` | авторизованные |
| Смена собственного пароля | `POST /auth/profile/password` | авторизованные |

## Скрипт создания администратора

```powershell
python scripts/create_admin.py                                   # спросит имя и пароль
python scripts/create_admin.py --name "Иванов Иван Иванович" --password "notary-2026"
```

## Переменные окружения (.env)

| Переменная | Назначение | По умолчанию |
| --- | --- | --- |
| `SECRET_KEY` | подпись JWT | `dev-secret-change-me` |
| `DATABASE_URL` | строка подключения | `sqlite+aiosqlite:///./portal.db` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | время жизни токена | `480` |

## Примечания

- Таблицы создаются автоматически при старте приложения (`Base.metadata.create_all`), миграции Alembic пока не настроены. При изменении схемы существующей базы колонку добавляют вручную, например:
  `ALTER TABLE users ADD COLUMN password_plain VARCHAR(128);`
- Пароли, заданные до появления просмотра, в открытом виде не сохранены (в списке видно «—»): администратору нужно выдать такой сотрудник новый пароль, после чего он появится в колонке «Пароль».
- `styles.css` в корне — утверждённый дизайн-код; рабочие шаблоны используют только его классы (файл-копия — `app/static/css/styles.css`).
