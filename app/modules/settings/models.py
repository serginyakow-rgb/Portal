"""Модели модуля «Настройки»: справочник тарифов и шаблоны карточек «Задач»."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InheritanceTariff(Base):
    """Строка справочника: вид имущества и региональный тариф по наследству."""

    __tablename__ = "inheritance_tariffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Вид имущества: «Квартира», «Жилой дом», «Земельный участок» и т. п.
    asset_type: Mapped[str] = mapped_column(String(200), nullable=False)
    # Региональный тариф — целое число больше нуля (проверяется схемой ввода)
    rate: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - отладочное представление
        return f"<InheritanceTariff id={self.id} asset_type={self.asset_type!r} rate={self.rate}>"


class CardTemplate(Base):
    """Шаблон карточки раздела «Задачи»: название и описания пунктов проверки.

    Таблицу создаёт ``Base.metadata.create_all`` при старте портала — как
    и остальные таблицы (миграции Alembic в проекте не ведутся).
    """

    __tablename__ = "card_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Название шаблона: «Договор дарения», «Договор купли-продажи» и т. п.
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # Пункты проверки по порядку — список описаний, тот же приём, что у чек-листа
    # карточки (tasks/models.py: Task.checklist). Хранятся только отмеченные
    # в окне «Добавить шаблон» строки; предел в 10 пунктов проверяет
    # схема ввода (schemas.py: CardTemplateInput). Пустой список разрешён.
    checks: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - отладочное представление
        return f"<CardTemplate id={self.id} title={self.title!r} checks={len(self.checks)}>"
