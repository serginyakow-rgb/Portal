"""Модели модуля «Резервное копирование».

Таблиц у модуля нет: файл копии собирается из моделей других модулей
(``auth.User``, ``settings.InheritanceTariff``, ``settings.CardTemplate``,
``templates_db``, ``tasks.Task``, ``tasks.Contact``) и из файлов Google
Календаря. Файл существует для единообразия структуры модуля
(``models.py``, ``schemas.py``, ``service.py``, ``routes.py``).
"""
