"""Модели модуля «Задачи»: карточки канбан-доски.

Модуль самодостаточен: модель User из модуля auth не импортируется. Внешние
ключи заданы строкой «users.id», а связи assignee и author разрешаются по
имени класса User, зарегистрированному в общем Base из app.db.base.
"""
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def now_utc() -> datetime:
    """Текущее время UTC без пояса — в том же виде, что CURRENT_TIMESTAMP в БД.

    Время пишет Python, а не только ``server_default``: ``CURRENT_TIMESTAMP``
    в SQLite хранит секунды, и две правки внутри одной секунды давали один
    и тот же ``updated_at``. По ``updated_at`` считается версия доски
    (``service.board_version``), поэтому нужна микросекундная точность.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Task(Base):
    """Карточка задачи: общие поля, чек-лист по типу и место на доске."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Исполнитель: ссылка на users.id, модуль auth не импортируется
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    # Тип карточки: gift, sale_minor, sale_other, inheritance, other,
    # spouse_consent, power_of_attorney (значения, подписи и чек-листы —
    # в schemas.py: CARD_TYPE_LABELS, CARD_TYPE_CHECKLISTS)
    card_type: Mapped[str] = mapped_column(String(20), nullable=False, default="other")
    # Столбец доски: queue, in_progress, review, done (см. STATUS_LABELS в schemas.py)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queue", index=True
    )
    # Чек-лист типа карточки: {название пункта: отмечен}
    checklist: Mapped[dict[str, bool]] = mapped_column(JSON, nullable=False, default=dict)
    # Автор карточки: ссылка на users.id
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        default=now_utc,
        onupdate=now_utc,
        nullable=False,
    )
    # Корзина: время удаления; пока NULL — карточка на доске
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Порядок внутри столбца: меньшее значение — выше карточка
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Исполнитель и автор читаются вместе с карточкой: в async-сессии ленивая
    # загрузка запрещена. foreign_keys обязателен — на users ведут два ключа.
    assignee = relationship("User", foreign_keys=[assignee_id], lazy="joined")
    author = relationship("User", foreign_keys=[created_by], lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover - отладочное представление
        return f"<Task id={self.id} title={self.title!r} status={self.status!r}>"
