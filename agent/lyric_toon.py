"""Lyric-toon renderer: stick-figure spotlight scene with timed handwritten lyrics.

Original artwork drawn in code (no third-party art). Audio must be royalty-free
or public domain: the caller supplies the file; see make_melody() for a
synthesised example.

Usage:
    python -m agent.lyric_toon spec.json out.mp4
spec.json = {"audio": "song.wav", "handle": "@apex_wealths",
             "intro": [{"t0": 0.0, "t1": 2.8, "text": "..."}],
             "lines": [{"t0": 3.0, "t1": 6.0, "text": "..."}]}
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
BG = (79, 77, 82)
YELLOW = (250, 236, 110)
INK = (12, 12, 14)
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
HAND = FONT_DIR / "patrick-hand-latin-400-normal.woff"
BOLD = FONT_DIR / "montserrat-latin-800-normal.woff"

SPOT_C = (540, 1560)
SPOT_R = 300
DOOR = (300, 480, 660, 1180)  # x0, y0, x1, y1 of the lit door face


def _gradient_polygon(size, poly, c0, c1, y0, y1, a0, a1):
    """RGBA layer: polygon filled with a vertical colour/alpha gradient."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    grad = Image.new("RGBA", size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    span = max(1, y1 - y0)
    for y in range(max(0, y0), min(size[1], y1)):
        t = (y - y0) / span
        col = tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
        gd.line([(0, y), (size[0], y)], fill=col + (int(a0 + (a1 - a0) * t),))
    layer.paste(grad, (0, 0), mask)
    return layer


def build_background() -> Image.Image:
    img = Image.new("RGBA", (W, H), BG + (255,))
    x0, y0, x1, y1 = DOOR
    # lit floor wedge below the door
    img.alpha_composite(_gradient_polygon(
        (W, H), [(x0, y1), (x1, y1), (x1 + 330, 1700), (x0 - 330, 1700)],
        YELLOW, BG, y1, 1700, 235, 0))
    # side wall of the doorway (yellow fading to grey)
    side = [(x1, y0), (x1 + 260, y0 + 90), (x1 + 260, y1 + 80), (x1, y1)]
    img.alpha_composite(_gradient_polygon((W, H), side, YELLOW, BG, y0, y1 + 80, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle(DOOR, fill=YELLOW)
    # outlines
    d.line([(x1, y0), (x1 + 260, y0 + 90), (x1 + 260, y1 + 80), (x1, y1)], fill=INK, width=7)
    d.line([(x0, y0), (x1, y0)], fill=INK, width=7)
    d.line([(x0, y0), (x0, y1)], fill=INK, width=7)
    d.line([(0, y1 + 40), (x0, y1), (x1, y1)], fill=INK, width=7)
    d.line([(x1, y1), (W, y1 + 330)], fill=INK, width=7)
    # small window on the far wall
    wx, wy = 880, 480
    d.rectangle([wx, wy, wx + 70, wy + 80], outline=INK, width=6)
    d.line([(wx + 35, wy), (wx + 35, wy + 80)], fill=INK, width=5)
    d.line([(wx, wy + 40), (wx + 70, wy + 40)], fill=INK, width=5)
    # spotlight beam from the top
    beam = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(beam)
    bd.polygon([(640, 0), (780, 0), (SPOT_C[0] + SPOT_R, SPOT_C[1]),
                (SPOT_C[0] - SPOT_R, SPOT_C[1])], fill=(215, 215, 220, 105))
    bd.ellipse([SPOT_C[0] - SPOT_R, SPOT_C[1] - SPOT_R * 0.62,
                SPOT_C[0] + SPOT_R, SPOT_C[1] + SPOT_R * 0.62], fill=(215, 215, 220, 150))
    img.alpha_composite(beam)
    return img.convert("RGB")


def _stick(d, p0, p1, w=7):
    d.line([p0, p1], fill=INK, width=w)


def draw_standing(d, t):
    """Man in the doorway: hat, mug, slow arm sway."""
    cx, top = 450, 640
    sway = math.sin(t * 2.2) * 8
    d.ellipse([cx - 38, top - 40, cx + 38, top + 36], outline=INK, width=7, fill=YELLOW)
    d.ellipse([cx - 70, top - 48, cx + 70, top - 20], fill=INK)          # hat brim
    d.rectangle([cx - 40, top - 98, cx + 40, top - 40], fill=INK)        # hat crown
    d.line([(cx - 14, top + 2), (cx - 14, top + 8)], fill=INK, width=6)  # eyes
    d.line([(cx + 14, top + 2), (cx + 14, top + 8)], fill=INK, width=6)
    d.arc([cx - 18, top + 14, cx + 18, top + 30], 20, 160, fill=INK, width=5)
    _stick(d, (cx, top + 36), (cx, top + 230))                           # body
    _stick(d, (cx, top + 230), (cx - 38, top + 410))                     # legs
    _stick(d, (cx, top + 230), (cx + 34, top + 410))
    _stick(d, (cx, top + 90), (cx - 60, top + 170))                      # arms
    hand = (cx + 86, top + 150 + sway)
    _stick(d, (cx, top + 90), hand)
    d.rectangle([hand[0] - 4, hand[1] - 4, hand[0] + 40, hand[1] + 34], fill=INK)  # mug


def draw_lying(d, t):
    """Tired figure on the floor with headphones, laptop and papers; head bobs to the beat."""
    cx, cy = SPOT_C[0] - 130, SPOT_C[1] + 20
    bob = math.sin(t * 2 * math.pi * 1.0) * 5
    d.ellipse([cx - 32, cy - 32 + bob, cx + 32, cy + 32 + bob], outline=INK, width=6, fill=(215, 215, 220))
    d.arc([cx - 42, cy - 42 + bob, cx + 42, cy + 20 + bob], 180, 360, fill=INK, width=7)  # headphones
    d.line([(cx - 4, cy - 4 + bob), (cx - 4, cy + 2 + bob)], fill=INK, width=5)
    d.line([(cx + 12, cy - 4 + bob), (cx + 12, cy + 2 + bob)], fill=INK, width=5)
    _stick(d, (cx + 32, cy + 6), (cx + 170, cy + 24), 6)                 # torso
    _stick(d, (cx + 170, cy + 24), (cx + 250, cy + 100), 6)              # legs
    _stick(d, (cx + 170, cy + 24), (cx + 270, cy + 60), 6)
    _stick(d, (cx + 70, cy + 14), (cx + 120, cy - 20), 6)                # arm to laptop
    lx, ly = cx + 150, cy - 70
    d.polygon([(lx, ly + 60), (lx + 90, ly + 60), (lx + 100, ly), (lx + 14, ly)], outline=INK, width=5)
    d.line([(lx - 6, ly + 66), (lx + 100, ly + 66)], fill=INK, width=5)
    for px, py, r in ((cx - 190, cy + 10, 6), (cx - 150, cy + 80, -10), (cx + 20, cy + 120, 4), (cx + 240, cy + 130, -4)):
        d.polygon([(px, py), (px + 50, py - r), (px + 56, py + 36), (px + 4, py + 40)], outline=INK, width=4)


def _text_layer(text: str, font_path: Path, size: int, box_w: int) -> Image.Image:
    """Word-wrapped, centred text on a transparent layer."""
    font = ImageFont.truetype(str(font_path), size)
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if font.getlength(trial) <= box_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    lh = int(size * 1.25)
    layer = Image.new("RGBA", (box_w + 20, lh * len(lines) + 10), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for i, ln in enumerate(lines):
        ld.text(((box_w + 20 - font.getlength(ln)) / 2, i * lh), ln, font=font, fill=INK + (255,))
    return layer


def _alpha(t: float, t0: float, t1: float, fade: float = 0.18) -> float:
    if t < t0 or t > t1:
        return 0.0
    return min(1.0, (t - t0) / fade, (t1 - t) / fade)


def render(spec: dict, out: Path) -> None:
    bg = build_background()
    intro = [(c["t0"], c["t1"], _text_layer(c["text"], BOLD, 34, 420)) for c in spec.get("intro", [])]
    lines = [(c["t0"], c["t1"], _text_layer(c["text"], HAND, 70, 880)) for c in spec["lines"]]
    handle = _text_layer(spec.get("handle", ""), BOLD, 22, 400) if spec.get("handle") else None
    audio = spec["audio"]
    total = max(c["t1"] for c in spec["lines"]) + 1.0
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", audio, "-t", f"{total:.2f}",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
           "-c:a", "aac", "-b:a", "160k", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,apad",
           "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for n in range(int(total * FPS)):
            t = n / FPS
            frame = bg.copy()
            d = ImageDraw.Draw(frame)
            draw_standing(d, t)
            draw_lying(d, t)
            rgba = frame.convert("RGBA")
            for t0, t1, layer in intro:
                a = _alpha(t, t0, t1)
                if a:
                    lay = layer.copy(); lay.putalpha(lay.getchannel("A").point(lambda v: int(v * a)))
                    rgba.alpha_composite(lay, (DOOR[0] + (DOOR[2] - DOOR[0] - lay.width) // 2, DOOR[1] - lay.height - 24))
            for t0, t1, layer in lines:
                a = _alpha(t, t0, t1)
                if a:
                    lay = layer.copy(); lay.putalpha(lay.getchannel("A").point(lambda v: int(v * a)))
                    rgba.alpha_composite(lay, (SPOT_C[0] - lay.width // 2, SPOT_C[1] - 250 - int((1 - a) * 18)))
            if handle:
                rgba.alpha_composite(handle, ((W - handle.width) // 2, H - 90))
            proc.stdin.write(rgba.convert("RGB").tobytes())
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed with exit code {rc}")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    spec = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    render(spec, Path(argv[2]))
    print(json.dumps({"video": argv[2]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
