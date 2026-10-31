"""Модуль «Резервное копирование»: один файл JSON со всеми данными портала.

Импорт модуля регистрирует разделы бэкапа (``sections.register_sections()``);
это и есть то самое «одно подключение» в ``app/main.py``: новый модуль со
своими данными описывает раздел в ``app/modules/<модуль>/backup.py`` и
добавляет один импорт, а ядро (``service.py``) остаётся неизменным.

Таблиц у модуля нет: данные лежат в таблицах других модулей.
"""
from app.modules.backup.sections import register_sections

# Разделы портала: users, inheritance, templates_db, tasks, google_calendar
register_sections()
