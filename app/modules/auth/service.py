"""Бизнес-логика пользователей: поиск, аутентификация, создание, правка и удаление."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.modules.auth.models import User
from app.modules.auth.schemas import UserCreate, name_key


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    """Возвращает пользователя по идентификатору (id берётся из JWT)."""
    return await db.get(User, user_id)


async def get_user_by_name(db: AsyncSession, full_name: str) -> User | None:
    """Возвращает пользователя по имени: регистр и лишние пробелы не важны."""
    key = name_key(full_name)
    result = await db.execute(select(User).where(User.name_key == key))
    user = result.scalar_one_or_none()
    if user is None:
        # Страховка для записей, созданных в обход сервиса (без ключа имени)
        result = await db.execute(select(User).where(func.lower(User.full_name) == key))
        user = result.scalars().first()
    return user


async def list_users(db: AsyncSession) -> list[User]:
    """Список сотрудников портала в алфавитном порядке."""
    result = await db.execute(select(User).order_by(User.full_name))
    return list(result.scalars().all())


async def create_user(db: AsyncSession, data: UserCreate) -> User:
    """Создаёт пользователя: логином становится его имя."""
    user = User(
        full_name=data.full_name,
        name_key=name_key(data.full_name),
        hashed_password=hash_password(data.password),
        password_plain=data.password,
        role=data.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def rename_user(db: AsyncSession, user: User, full_name: str) -> User:
    """Меняет имя пользователя (оно же логин); текущая сессия остаётся рабочей."""
    user.full_name = full_name
    user.name_key = name_key(full_name)
    await db.commit()
    await db.refresh(user)
    return user


async def set_password(db: AsyncSession, user: User, password: str) -> User:
    """Задаёт пароль: хранится bcrypt-хеш (для входа) и сам пароль (для просмотра админом)."""
    user.hashed_password = hash_password(password)
    user.password_plain = password
    await db.commit()
    await db.refresh(user)
    return user


async def update_user(
    db: AsyncSession,
    user: User,
    *,
    full_name: str,
    password: str = "",
) -> User:
    """Правка сотрудника администратором: новое имя и, если пароль задан, новый пароль."""
    if user.full_name != full_name:
        user = await rename_user(db, user, full_name)
    if password:
        user = await set_password(db, user, password)
    return user


async def delete_user(db: AsyncSession, user: User) -> None:
    """Удаляет сотрудника портала вместе с его учётной записью."""
    await db.delete(user)
    await db.commit()


async def authenticate_user(db: AsyncSession, full_name: str, password: str) -> User | None:
    """Проверяет имя и пароль; возвращает пользователя только при полном совпадении."""
    user = await get_user_by_name(db, full_name)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
