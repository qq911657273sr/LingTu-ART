from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
SIZE = 1024

gradient = Image.new("RGB", (SIZE, SIZE))
pixels = gradient.load()
start, end = (37, 42, 50), (13, 15, 19)
for y in range(SIZE):
    for x in range(SIZE):
        t = (x + y) / (2 * (SIZE - 1))
        pixels[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(start, end))

mask = Image.new("L", (SIZE, SIZE), 0)
ImageDraw.Draw(mask).rounded_rectangle((32, 32, 992, 992), radius=238, fill=255)
icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
ImageDraw.Draw(shadow).rounded_rectangle((26, 38, 998, 1004), radius=246, fill=(0, 0, 0, 100))
icon.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(24)))
icon.paste(gradient, (0, 0), mask)

draw = ImageDraw.Draw(icon)
draw.rounded_rectangle((33, 33, 991, 991), radius=237, outline=(255, 255, 255, 23), width=3)
draw.rounded_rectangle((178, 178, 846, 846), radius=194, fill=(8, 10, 13, 255), outline=(255, 255, 255, 18), width=4)

lime = Image.new("RGB", (1, 210))
lp = lime.load()
for y in range(210):
    t = y / 209
    lp[0, y] = (round(226 + (173 - 226) * t), round(255 + (240 - 255) * t), round(54 + (0 - 54) * t))
tiles = [(268, 268), (546, 268), (268, 546), (546, 546)]
for x, y in tiles:
    tile_mask = Image.new("L", (210, 210), 0)
    ImageDraw.Draw(tile_mask).rounded_rectangle((0, 0, 209, 209), radius=72, fill=255)
    tile = lime.resize((210, 210)).convert("RGBA")
    icon.paste(tile, (x, y), tile_mask)

draw = ImageDraw.Draw(icon)
draw.polygon([(751, 203), (766, 242), (805, 257), (766, 272), (751, 311), (736, 272), (697, 257), (736, 242)], fill=(242, 255, 157, 255))

preview = OUT / "Artspace-Studio-icon.png"
preview.parent.mkdir(parents=True, exist_ok=True)
icon.save(preview)
icon_path = ROOT / "packaging" / "artspace.ico"
icon.save(icon_path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"Wrote {preview}")
print(f"Wrote {icon_path}")
