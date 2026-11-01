"""Lyric-toon renderer: dark room, the door swings open, a man steps in and talks,
then a spotlight clicks on over a tired figure and timed handwritten lines appear.

All artwork is drawn in code. Audio is optional: without it the video is silent, so
licensed music can be added inside Instagram / YouTube (their libraries carry the licence).

Usage:  python -m agent.lyric_toon spec.json out.mp4
spec = {"audio": "optional.wav", "handle": "@name", "upper": true,
        "door": [0.3, 1.4], "walk": [1.4, 2.2], "beam_t": 6.0,
        "intro": [{"t0": 2.3, "t1": 4.0, "text": "...", "mood": "happy"}],
        "lines": [{"t0": 6.6, "t1": 9.0, "text": "..."}]}
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
DARK = (44, 43, 47)
YELLOW = (250, 236, 110)
INK = (12, 12, 14)
LW = 9
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
HAND = FONT_DIR / "patrick-hand-latin-400-normal.woff"
BOLD = FONT_DIR / "montserrat-latin-800-normal.woff"

SPOT_C = (540, 1560)
SPOT_R = 330
DOOR = (250, 470, 640, 1200)  # door face: x0, y0, x1, y1
CORD_X = 735


def _grad_poly(poly, c0, c1, y0, y1, a0, a1):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    span = max(1, y1 - y0)
    for y in range(max(0, y0), min(H, y1)):
        t = (y - y0) / span
        col = tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
        gd.line([(0, y), (W, y)], fill=col + (int(a0 + (a1 - a0) * t),))
    layer.paste(grad, (0, 0), mask)
    return layer


def build_scene(lit: bool) -> Image.Image:
    """Room and door frame. lit=False: doorway is dark; lit=True: yellow light spills out."""
    x0, y0, x1, y1 = DOOR
    img = Image.new("RGBA", (W, H), BG + (255,))
    if lit:
        img.alpha_composite(_grad_poly([(x0, y1), (x1, y1), (x1 + 380, 1760), (x0 - 380, 1760)],
                                       YELLOW, BG, y1, 1760, 240, 0))
        side = [(x1, y0), (x1 + 280, y0 + 100), (x1 + 280, y1 + 90), (x1, y1)]
        img.alpha_composite(_grad_poly(side, YELLOW, BG, y0, y1 + 90, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle(DOOR, fill=YELLOW if lit else DARK)
    d.line([(x1, y0), (x1 + 280, y0 + 100), (x1 + 280, y1 + 90), (x1, y1)], fill=INK, width=LW)
    d.line([(x0, y0), (x1, y0)], fill=INK, width=LW)
    d.line([(x0, y0), (x0, y1)], fill=INK, width=LW)
    d.line([(0, y1 + 50), (x0, y1), (x1, y1)], fill=INK, width=LW)
    d.line([(x1, y1), (W, y1 + 360)], fill=INK, width=LW)
    wx, wy = 900, 520  # window
    d.rectangle([wx, wy, wx + 80, wy + 90], outline=INK, width=7)
    d.line([(wx + 40, wy), (wx + 40, wy + 90)], fill=INK, width=6)
    d.line([(wx, wy + 45), (wx + 80, wy + 45)], fill=INK, width=6)
    d.line([(CORD_X, 0), (CORD_X, 420)], fill=INK, width=6)  # ceiling cord
    d.ellipse([CORD_X - 11, 420, CORD_X + 11, 442], fill=INK)
    return img.convert("RGB")


def build_beam() -> Image.Image:
    beam = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(beam)
    bd.polygon([(CORD_X - 60, 0), (CORD_X + 60, 0), (SPOT_C[0] + SPOT_R, SPOT_C[1]),
                (SPOT_C[0] - SPOT_R, SPOT_C[1])], fill=(215, 215, 220, 105))
    bd.ellipse([SPOT_C[0] - SPOT_R, SPOT_C[1] - SPOT_R * 0.62, SPOT_C[0] + SPOT_R, SPOT_C[1] + SPOT_R * 0.62],
               fill=(215, 215, 220, 155))
    return beam


def _line(d, a, b, w=LW):
    d.line([a, b], fill=INK, width=w)


def draw_man(d, t, mood="happy", dx=0):
    """Man in a hat with a cigarette and a mug. mood: happy | sad."""
    cx, top = 445 + dx, 640
    sway = math.sin(t * 2.4) * 9
    d.ellipse([cx - 46, top - 46, cx + 46, top + 46], outline=INK, width=LW, fill=YELLOW)
    d.ellipse([cx - 82, top - 56, cx + 82, top - 22], fill=INK)  # brim
    d.rectangle([cx - 46, top - 112, cx + 46, top - 46], fill=INK)  # crown
    d.rectangle([cx - 46, top - 70, cx + 46, top - 56], fill=(120, 120, 128))  # hat band
    d.line([(cx - 17, top - 2), (cx - 17, top + 8)], fill=INK, width=7)  # eyes
    d.line([(cx + 17, top - 2), (cx + 17, top + 8)], fill=INK, width=7)
    if mood == "happy":
        d.arc([cx - 24, top + 8, cx + 24, top + 34], 15, 165, fill=INK, width=6)
    else:
        d.arc([cx - 22, top + 22, cx + 22, top + 44], 195, 345, fill=INK, width=6)
        d.line([(cx - 28, top - 14), (cx - 8, top - 8)], fill=INK, width=5)  # worried brows
        d.line([(cx + 28, top - 14), (cx + 8, top - 8)], fill=INK, width=5)
    sx, sy = cx + 40, top + 24  # cigarette + smoke
    d.line([(sx, sy), (sx + 36, sy - 14)], fill=INK, width=7)
    for i in range(3):
        px = sx + 46 + math.sin(t * 3 + i) * 7
        d.line([(px, sy - 28 - i * 22), (px + 9, sy - 48 - i * 22)], fill=INK, width=4)
    _line(d, (cx, top + 46), (cx, top + 250))  # body
    _line(d, (cx, top + 250), (cx - 44, top + 440))  # legs
    _line(d, (cx, top + 250), (cx + 40, top + 440))
    _line(d, (cx, top + 100), (cx - 70, top + 190))  # arms
    hand = (cx + 96, top + 165 + sway)
    _line(d, (cx, top + 100), hand)
    d.rounded_rectangle([hand[0] - 6, hand[1] - 4, hand[0] + 50, hand[1] + 44], 6, fill=INK)  # mug


def draw_lying(d, t):
    """Tired figure on the floor: headphones, laptop, phones, papers; head bobs slowly."""
    cx, cy = SPOT_C[0] - 150, SPOT_C[1] + 30
    bob = math.sin(t * 2 * math.pi) * 5
    d.ellipse([cx - 40, cy - 40 + bob, cx + 40, cy + 40 + bob], outline=INK, width=7, fill=(215, 215, 220))
    d.arc([cx - 52, cy - 52 + bob, cx + 52, cy + 26 + bob], 180, 360, fill=INK, width=8)
    d.ellipse([cx - 56, cy - 12 + bob, cx - 38, cy + 18 + bob], fill=INK)
    d.line([(cx - 8, cy - 4 + bob), (cx - 8, cy + 4 + bob)], fill=INK, width=6)
    d.line([(cx + 14, cy - 4 + bob), (cx + 14, cy + 4 + bob)], fill=INK, width=6)
    d.arc([cx - 10, cy + 12 + bob, cx + 20, cy + 26 + bob], 190, 350, fill=INK, width=5)
    _line(d, (cx + 40, cy + 8), (cx + 200, cy + 30), 7)
    _line(d, (cx + 200, cy + 30), (cx + 290, cy + 115), 7)
    _line(d, (cx + 200, cy + 30), (cx + 310, cy + 70), 7)
    _line(d, (cx + 80, cy + 18), (cx + 140, cy - 24), 7)
    lx, ly = cx + 170, cy - 90
    d.polygon([(lx, ly + 70), (lx + 106, ly + 70), (lx + 118, ly), (lx + 16, ly)], outline=INK, width=6)
    d.line([(lx - 8, ly + 78), (lx + 120, ly + 78)], fill=INK, width=6)
    for px, py, r in ((cx - 230, cy + 10, 7), (cx - 170, cy + 96, -10), (cx + 10, cy + 140, 5),
                      (cx + 260, cy + 150, -5), (cx - 250, cy + 130, 9)):
        d.polygon([(px, py), (px + 58, py - r), (px + 64, py + 42), (px + 5, py + 46)], outline=INK, width=5)
    d.rounded_rectangle([cx + 60, cy + 90, cx + 92, cy + 140], 5, outline=INK, width=5)  # phone


def _text_layer(text, font_path, size, box_w):
    font = ImageFont.truetype(str(font_path), size)
    lines, cur = [], ""
    for w in text.split():
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


def _alpha(t, t0, t1, fade=0.18):
    if t < t0 or t > t1:
        return 0.0
    return min(1.0, (t - t0) / fade, (t1 - t) / fade)


def _fade(layer, a):
    out = layer.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * a)))
    return out


def _mood_at(t, intro):
    for t0, t1, mood, _ in intro:
        if t0 <= t <= t1:
            return mood
    last = max((c[1] for c in intro), default=0)
    return "sad" if t > last else "happy"


def _draw_door_and_man(frame, t, p, door1, walk0, walk1, intro):
    d = ImageDraw.Draw(frame)
    if 0 < p < 1:  # door leaf swings open, hinged on the right
        lw = int((DOOR[2] - DOOR[0]) * (1 - p))
        d.rectangle([DOOR[2] - lw, DOOR[1], DOOR[2], DOOR[3]], fill=(60, 58, 62), outline=INK, width=LW)
    if t < door1 - 0.1:
        return
    wp = min(1.0, max(0.0, (t - walk0) / (walk1 - walk0)))
    dx = int((1 - wp) * 260)
    mood = _mood_at(t, intro)
    if not dx:
        draw_man(d, t, mood, 0)
        return
    tmp = frame.copy()  # man walks in from the right, clipped to the doorway
    draw_man(ImageDraw.Draw(tmp), t, mood, dx)
    box = (DOOR[0] + LW, DOOR[1] + LW, DOOR[2] - LW, DOOR[3] - LW)
    frame.paste(tmp.crop(box), box[:2])


def render(spec: dict, out: Path) -> None:
    dark, lit, beam = build_scene(False), build_scene(True), build_beam()
    door0, door1 = spec.get("door", [0.3, 1.4])
    walk0, walk1 = spec.get("walk", [1.4, 2.2])
    beam_t = spec["beam_t"]
    upper = spec.get("upper", True)
    intro = [(c["t0"], c["t1"], c.get("mood", "happy"), _text_layer(c["text"], BOLD, 36, 440))
             for c in spec.get("intro", [])]
    lines = [(c["t0"], c["t1"], _text_layer(c["text"].upper() if upper else c["text"], HAND, 72, 900))
             for c in spec["lines"]]
    handle = _text_layer(spec["handle"], BOLD, 22, 400) if spec.get("handle") else None
    total = max(c["t1"] for c in spec["lines"]) + 1.0

    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-"]
    if spec.get("audio"):
        cmd += ["-i", spec["audio"], "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,apad"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono"]
    cmd += ["-t", f"{total:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
            "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for n in range(int(total * FPS)):
            t = n / FPS
            p = min(1.0, max(0.0, (t - door0) / (door1 - door0)))
            frame = lit.copy() if p >= 1 else Image.blend(dark, lit, p)
            _draw_door_and_man(frame, t, p, door1, walk0, walk1, intro)
            rgba = frame.convert("RGBA")
            if t >= beam_t:
                ba = min(1.0, (t - beam_t) / 0.4)
                fig = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                draw_lying(ImageDraw.Draw(fig), t)
                rgba.alpha_composite(_fade(beam, ba))
                rgba.alpha_composite(_fade(fig, ba))
            for t0, t1, _m, layer in intro:
                a = _alpha(t, t0, t1)
                if a:
                    pos = (DOOR[0] + (DOOR[2] - DOOR[0] - layer.width) // 2, DOOR[1] - layer.height - 24)
                    rgba.alpha_composite(_fade(layer, a), pos)
            for t0, t1, layer in lines:
                a = _alpha(t, t0, t1)
                if a:
                    rgba.alpha_composite(_fade(layer, a),
                                         (SPOT_C[0] - layer.width // 2, SPOT_C[1] - 255 - int((1 - a) * 18)))
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
