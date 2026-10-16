"""Модель пользователя портала нотариальной конторы."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """Сотрудник портала. Логином служит имя (ФИО) на русском языке."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Полное имя (ФИО) — оно же логин для входа
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Ключ имени: регистр и повторные пробелы приведены к единому виду (защита от дублей)
    name_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # Пароль в открытом виде: администратор должен видеть, какой пароль выдан сотруднику.
    # У старых записей поле пустое: им пароль выдают заново в разделе «Пользователи».
    password_plain: Mapped[str | None] = mapped_column(String(128), nullable=True)

    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - отладочное представление
        return f"<User id={self.id} full_name={self.full_name!r} role={self.role!r}>"
