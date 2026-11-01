"""Значок приложения: собирает ``portal.ico`` из ``logo.jpg``.

Значок нужен в трёх местах: файл ``Portal.exe``, установщик (``SetupIconFile``)
и значок в трее. Windows берёт из ICO размер под контекст (панель задач,
проводник, меню «Пуск»), поэтому в файл кладётся набор размеров.
"""
from pathlib import Path

from PIL import Image

# Размеры, которые Windows запрашивает для файла, ярлыка и трея
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
# Сторона квадратного полотна значка
CANVAS = 256

DESKTOP_DIR = Path(__file__).resolve().parent
ROOT = DESKTOP_DIR.parent
SOURCE = ROOT / "logo.jpg"
TARGET = DESKTOP_DIR / "portal.ico"


def square(image: Image.Image) -> Image.Image:
    """Обрезает картинку по центру до квадрата со стороной 256 точек."""
    converted = image.convert("RGBA")
    side = min(converted.size)
    left = (converted.width - side) // 2
    top = (converted.height - side) // 2
    cropped = converted.crop((left, top, left + side, top + side))
    return cropped.resize((CANVAS, CANVAS), Image.LANCZOS)


def build_icon() -> Path:
    """Создаёт ``portal.ico`` рядом с этим файлом и возвращает путь к нему."""
    if not SOURCE.exists():
        raise SystemExit(f"Не найден исходный логотип: {SOURCE}")
    image = square(Image.open(SOURCE))
    image.save(TARGET, format="ICO", sizes=[(size, size) for size in ICON_SIZES])
    return TARGET


if __name__ == "__main__":
    print(f"Значок собран: {build_icon()}")
