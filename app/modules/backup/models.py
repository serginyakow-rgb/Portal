"""Модели модуля «Резервное копирование».

Таблиц у модуля нет: файл копии собирается из моделей других модулей
(``auth.User``, ``settings.InheritanceTariff``, ``templates_db``, ``tasks.Task``)
и из файлов Google Календаря. Файл существует для единообразия структуры
модуля (``models.py``, ``schemas.py``, ``service.py``, ``routes.py``).
"""
