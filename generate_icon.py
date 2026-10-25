#!/usr/bin/env python3
"""Автоматический генератор файла icon.ico с сине-голубым алмазиком."""

from PIL import Image, ImageDraw

def create_diamond_icon():
    sizes = [(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)]
    images = []

    for size in sizes:
        w, h = size
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Центр и масштабирование
        cx, cy = w / 2, h / 2
        r = min(w, h) * 0.42

        # Точки кристалла
        top = (cx, cy - r)
        bottom = (cx, cy + r)
        left = (cx - r * 0.9, cy - r * 0.2)
        right = (cx + r * 0.9, cy - r * 0.2)
        mid_left = (cx - r * 0.45, cy - r * 0.2)
        mid_right = (cx + r * 0.45, cy - r * 0.2)

        # Грани алмаза
        # Верхняя площадка
        draw.polygon([left, mid_left, mid_right, right, top], fill=(96, 165, 250, 255))
        # Центральная грань
        draw.polygon([mid_left, mid_right, bottom], fill=(59, 130, 246, 255))
        # Левая нижняя грань
        draw.polygon([left, mid_left, bottom], fill=(37, 99, 235, 255))
        # Правая нижняя грань
        draw.polygon([right, mid_right, bottom], fill=(29, 78, 216, 255))
        # Верхние срезы
        draw.polygon([top, left, mid_left], fill=(147, 197, 253, 255))
        draw.polygon([top, right, mid_right], fill=(191, 219, 254, 255))

        images.append(img)

    # Сохранение ICO со всеми размерами
    images[0].save("icon.ico", format="ICO", sizes=sizes)
    print("Иконка icon.ico успешно создана!")

if __name__ == "__main__":
    create_diamond_icon()