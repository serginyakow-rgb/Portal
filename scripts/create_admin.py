"""Создание администратора портала: имя на русском и пароль."""
import argparse
import asyncio
import sys
from getpass import getpass
from pathlib import Path

# Корень проекта в sys.path, чтобы скрипт запускался из любой папки
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError  # noqa: E402

from app.core.database import async_session_maker, engine  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.modules.auth import models as auth_models  # noqa: E402,F401
from app.modules.auth.schemas import UserCreate  # noqa: E402
from app.modules.auth.service import create_user, get_user_by_name  # noqa: E402


def _prompt_full_name() -> str:
    """Спрашивает имя администратора (вход будет выполняться по этому имени)."""
    return input("Имя администратора (ФИО): ").strip()


async def create_admin(full_name: str, password: str) -> int:
    """Создаёт администратора портала; возвращает код выхода процесса."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        data = UserCreate(full_name=full_name, password=password, role="admin")
    except ValidationError as exc:
        message = str(exc.errors()[0].get("msg", "Некорректные данные"))
        print(f"Ошибка: {message.removeprefix('Value error, ')}")
        await engine.dispose()
        return 1

    async with async_session_maker() as session:
        if await get_user_by_name(session, data.full_name) is not None:
            print(f"Пользователь «{data.full_name}» уже существует")
            await engine.dispose()
            return 1
        user = await create_user(session, data)
        print(f"Администратор создан: {user.full_name} (id={user.id})")

    await engine.dispose()
    print("Вход в портал — по этому имени и паролю.")
    return 0


def main() -> int:
    """Разбирает аргументы командной строки и запускает создание администратора."""
    parser = argparse.ArgumentParser(
        description="Создание администратора портала нотариальной конторы (вход по имени)",
    )
    parser.add_argument("--name", help="Имя администратора на русском: «Иванов Иван Иванович»")
    parser.add_argument("--password", help="Пароль (если не указан, будет запрошен скрытно)")
    args = parser.parse_args()

    full_name = args.name or _prompt_full_name()
    password = args.password or getpass("Пароль: ")
    return asyncio.run(create_admin(full_name, password))


if __name__ == "__main__":
    raise SystemExit(main())
