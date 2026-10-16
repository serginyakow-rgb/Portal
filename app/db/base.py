"""Единый декларативный Base для всех моделей проекта."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс моделей SQLAlchemy 2.0 — наследуют все модели портала."""

    pass
