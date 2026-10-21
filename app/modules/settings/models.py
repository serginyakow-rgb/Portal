"""Модели модуля «Настройки»: справочник региональных тарифов для наследства."""
from sqlalchemy import Integer, String
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
