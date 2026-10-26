"""Diqqatni tortuvchi muqova (thumbnail): videodan kadr + katta, qiziqtiruvchi yozuv."""
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from .utils import ROOT, log, run

FALLBACK_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
YELLOW = (255, 212, 0)
RED = (230, 30, 45)


def _font_path(cfg: dict) -> str:
    for p in [ROOT / cfg["subtitles"]["font_file"], *map(Path, FALLBACK_FONTS)]:
        if p.exists():
            return str(p)
    raise RuntimeError("Shrift topilmadi")


def _clean(text: str) -> str:
    # Emoji va shriftda yo'q belgilarni olib tashlaymiz
    text = "".join(ch for ch in text if ord(ch) < 0x2000)
    return re.sub(r"\s+", " ", text).strip().upper()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if not cur or draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit(draw, text: str, font_path: str, max_w: int, max_lines: int, start: int = 170, min_size: int = 80):
    """Matnni max_lines qatorga sig'adigan eng katta shrift o'lchami."""
    size = start
    while size >= min_size:
        font = ImageFont.truetype(font_path, size)
        lines = _wrap(draw, text, font, max_w)
        if len(lines) <= max_lines and all(draw.textlength(l, font=font) <= max_w for l in lines):
            return font, lines
        size -= 8
    font = ImageFont.truetype(font_path, min_size)
    return font, _wrap(draw, text, font, max_w)[:max_lines]


def _badge(draw, text: str, font, center_x: float, y: float, fill, color) -> float:
    w = draw.textlength(text, font=font)
    pad_x, pad_y = 40, 22
    asc, desc = font.getmetrics()
    box = [center_x - w / 2 - pad_x, y, center_x + w / 2 + pad_x, y + asc + desc + 2 * pad_y]
    draw.rounded_rectangle(box, radius=28, fill=fill)
    draw.text((center_x - w / 2, y + pad_y), text, font=font, fill=color)
    return box[3]


def make_thumbnail(video: Path, story: dict, cfg: dict, out: Path) -> Path:
    W, H = cfg["video"]["width"], cfg["video"]["height"]
    frame = out.with_name("thumb_frame.jpg")
    run(["ffmpeg", "-y", "-ss", "1.5", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(frame)])
    img = Image.open(frame).convert("RGB").resize((W, H))
    img = ImageEnhance.Brightness(img).enhance(0.6)
    img = ImageEnhance.Contrast(img).enhance(1.15)

    # Yozuv yaxshi o'qilishi uchun tepa va pastni qoraytiramiz
    shade = Image.new("L", (1, H))
    for y in range(H):
        shade.putpixel((0, y), int(170 * (abs(y - H / 2) / (H / 2)) ** 1.6))
    img.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0), shade.resize((W, H)))

    draw = ImageDraw.Draw(img)
    fp = _font_path(cfg)
    text = _clean(story.get("thumbnail_text") or story.get("hook") or story["title"])

    y = _badge(draw, "BILARMIDINGIZ?", ImageFont.truetype(fp, 78), W / 2, 170, YELLOW, (0, 0, 0)) + 70
    font, lines = _fit(draw, text, fp, W - 120, 5)
    lh = sum(font.getmetrics()) + 10
    y = max(y, (H - lh * len(lines)) // 2 - 80)
    for i, line in enumerate(lines):
        w = draw.textlength(line, font=font)
        # Oxirgi qatorni sariq qilib ajratamiz — ko'z o'sha yerga tushadi
        color = YELLOW if i == len(lines) - 1 and len(lines) > 1 else (255, 255, 255)
        draw.text(((W - w) / 2, y), line, font=font, fill=color, stroke_width=12, stroke_fill=(0, 0, 0))
        y += lh

    _badge(draw, "OXIRIGACHA KO'RING!", ImageFont.truetype(fp, 64), W / 2, H - 420, RED, (255, 255, 255))
    img.save(out, "JPEG", quality=90)
    log.info("Muqova tayyor: %s", out.name)
    return out
