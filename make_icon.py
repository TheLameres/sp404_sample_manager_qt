#!/usr/bin/env python3
"""
make_icon.py — генерирует icon.png (1024×1024) в стиле SP-404SX.
На macOS build_macos.sh конвертирует его в icon.icns через iconutil/sips.

Запуск: python make_icon.py
"""
from PIL import Image, ImageDraw, ImageFont


def make_icon(size=1024, out="icon.png"):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Скруглённый тёмный фон (корпус устройства)
    margin = int(size * 0.06)
    radius = int(size * 0.20)
    d.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius, fill=(20, 20, 26, 255),
        outline=(255, 92, 56, 255), width=int(size * 0.012),
    )

    # Сетка пэдов 4×3 (как на SP-404SX)
    pad_area_top = int(size * 0.20)
    pad_area_left = int(size * 0.16)
    pad_area_w = int(size * 0.68)
    gap = int(size * 0.035)
    cols, rows = 4, 3
    pad_w = (pad_area_w - gap * (cols - 1)) // cols
    pad_h = pad_w

    # Акцентные цвета пэдов (категории)
    colors = [
        (230, 57, 70), (247, 127, 0), (252, 191, 73), (201, 180, 88),
        (67, 97, 238), (42, 157, 143), (131, 56, 236), (58, 134, 255),
        (6, 214, 160), (239, 71, 111), (214, 40, 40), (108, 117, 125),
    ]

    idx = 0
    for r in range(rows):
        for c in range(cols):
            x0 = pad_area_left + c * (pad_w + gap)
            y0 = pad_area_top + r * (pad_h + gap)
            col = colors[idx % len(colors)]
            # Пэд с лёгким свечением
            d.rounded_rectangle(
                [x0, y0, x0 + pad_w, y0 + pad_h],
                radius=int(pad_w * 0.18),
                fill=(col[0], col[1], col[2], 235),
                outline=(255, 255, 255, 40), width=max(2, int(size * 0.003)),
            )
            idx += 1

    # Подпись «404» внизу
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            int(size * 0.11))
    except Exception:
        font = ImageFont.load_default()
    text = "404"
    bbox = d.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    d.text(((size - tw) / 2, int(size * 0.80)), text,
           fill=(255, 92, 56, 255), font=font)

    img.save(out)
    print(f"✅ Saved {out} ({size}×{size})")
    return out


if __name__ == "__main__":
    make_icon()
