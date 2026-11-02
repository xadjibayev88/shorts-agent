"""Lyric-toon renderer: dark room, the door swings open, a man steps in and talks,
then a spotlight clicks on over a tired figure and timed handwritten lines appear.

All artwork is drawn in code (agent/toon_art.py). Audio is optional: without it the video
is silent, so licensed music can be added inside Instagram / YouTube.

Usage:  python -m agent.lyric_toon spec.json out.mp4
spec = {"audio": "optional.wav", "audio_licensed": true, "handle": "@name", "upper": true,
        "door": [0.3, 1.4], "walk": [1.4, 2.2], "beam_t": 6.0,
        "intro": [{"t0": 2.3, "t1": 4.0, "text": "...", "mood": "happy"}],
        "lines": [{"t0": 6.6, "t1": 9.0, "text": "..."}]}
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .toon_art import BOIL_FPS, SD, SS, draw_lying, draw_man, draw_room

W, H, FPS = 1080, 1920, 30
BG = (79, 77, 82)
DARK = (44, 43, 47)
YELLOW = (250, 236, 110)
INK = (14, 14, 18)
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
HAND = FONT_DIR / "patrick-hand-latin-400-normal.woff"
BOLD = FONT_DIR / "montserrat-latin-800-normal.woff"

SPOT_C = (540, 1560)
SPOT_R = 330
DOOR = (250, 470, 640, 1200)
MAN_BOX = DOOR
LIE_BOX = (120, 1300, 960, 1860)
FLICKER = (0.2, 0.9, 0.3, 1.0, 0.6, 1.0)  # spotlight stutters on, like an old bulb
PUSH_IN = 0.035  # slow camera zoom over the whole video


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


def _downsample(img: Image.Image) -> Image.Image:
    return img.resize((img.width // SS, img.height // SS), Image.LANCZOS)


def build_scene(lit: bool, outline: Image.Image) -> Image.Image:
    x0, y0, x1, y1 = DOOR
    img = Image.new("RGBA", (W, H), BG + (255,))
    if lit:
        img.alpha_composite(_grad_poly([(x0, y1), (x1, y1), (x1 + 380, 1760), (x0 - 380, 1760)],
                                       YELLOW, BG, y1, 1760, 240, 0))
        side = [(x1, y0), (x1 + 280, y0 + 100), (x1 + 280, y1 + 90), (x1, y1)]
        img.alpha_composite(_grad_poly(side, YELLOW, BG, y0, y1 + 90, 255, 255))
    ImageDraw.Draw(img).rectangle(DOOR, fill=YELLOW if lit else DARK)
    img.alpha_composite(outline)
    return img.convert("RGB")


def build_beam() -> Image.Image:
    beam = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    bd = ImageDraw.Draw(beam)
    cx, cy, r = SPOT_C[0] * SS, SPOT_C[1] * SS, SPOT_R * SS
    bd.polygon([(675 * SS, 0), (795 * SS, 0), (cx + r, cy), (cx - r, cy)], fill=(215, 215, 220, 105))
    bd.ellipse([cx - r, cy - r * 0.62, cx + r, cy + r * 0.62], fill=(215, 215, 220, 155))
    return _downsample(beam).filter(ImageFilter.GaussianBlur(2.5))


def _layer(box, draw_fn, t, *args) -> Image.Image:
    """Draw characters into a supersampled transparent layer for `box`, then downsample."""
    x0, y0, x1, y1 = box
    img = Image.new("RGBA", ((x1 - x0) * SS, (y1 - y0) * SS), (0, 0, 0, 0))
    draw_fn(SD(img, x0, y0, boil=int(t * BOIL_FPS)), t, *args)
    return _downsample(img)


def _text_layer(text, font_path, size, box_w, tilt=0.0):
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
    return layer.rotate(tilt, resample=Image.BICUBIC, expand=True) if tilt else layer


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
    return "sad" if t > max((c[1] for c in intro), default=0) else "happy"


def _beam_alpha(t, beam_t):
    if t < beam_t:
        return 0.0
    k = int((t - beam_t) * FPS)
    return FLICKER[k] if k < len(FLICKER) else min(1.0, 0.85 + (t - beam_t) * 0.15)


def _push_in(img: Image.Image, t, total) -> Image.Image:
    z = 1 + PUSH_IN * min(1.0, t / total)
    cw, ch = W / z, H / z
    x, y = (W - cw) / 2, (H - ch) / 2
    return img.resize((W, H), Image.BICUBIC, box=(x, y, x + cw, y + ch))


def _grain(rng) -> np.ndarray:
    n = rng.integers(-7, 8, size=(H, W), dtype=np.int16)
    return np.repeat(n[:, :, None], 3, axis=2)


def _compose(t, ctx) -> Image.Image:
    door0, door1 = ctx["door"]
    p = min(1.0, max(0.0, (t - door0) / (door1 - door0)))
    frame = ctx["lit"].copy() if p >= 1 else Image.blend(ctx["dark"], ctx["lit"], p)
    if 0 < p < 1:  # door leaf swings open, hinged on the right
        lw = int((DOOR[2] - DOOR[0]) * (1 - p))
        ImageDraw.Draw(frame).rectangle([DOOR[2] - lw, DOOR[1], DOOR[2], DOOR[3]], fill=(60, 58, 62),
                                        outline=INK, width=5)
    rgba = frame.convert("RGBA")
    if t >= door1 - 0.1:
        walk0, walk1 = ctx["walk"]
        dx = int((1 - min(1.0, max(0.0, (t - walk0) / (walk1 - walk0)))) * 260)
        man = _layer(MAN_BOX, draw_man, t, _mood_at(t, ctx["intro"]), dx)
        rgba.alpha_composite(man, MAN_BOX[:2])
    ba = _beam_alpha(t, ctx["beam_t"])
    if ba:
        rgba.alpha_composite(_fade(ctx["beam"], ba))
        rgba.alpha_composite(_fade(_layer(LIE_BOX, draw_lying, t), ba), LIE_BOX[:2])
    for t0, t1, _m, layer in ctx["intro"]:
        a = _alpha(t, t0, t1)
        if a:
            pos = (DOOR[0] + (DOOR[2] - DOOR[0] - layer.width) // 2, DOOR[1] - layer.height - 24)
            rgba.alpha_composite(_fade(layer, a), pos)
    for t0, t1, layer in ctx["lines"]:
        a = _alpha(t, t0, t1)
        if a:
            rgba.alpha_composite(_fade(layer, a), (SPOT_C[0] - layer.width // 2, SPOT_C[1] - 255 - int((1 - a) * 18)))
    return rgba.convert("RGB")


def _finish(img: Image.Image, t, ctx) -> bytes:
    out = _push_in(img, t, ctx["total"])
    arr = np.asarray(out, dtype=np.int16) + ctx["grain"][int(t * FPS) % len(ctx["grain"])]
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    if ctx["handle"] is not None:
        rgba = out.convert("RGBA")
        rgba.alpha_composite(ctx["handle"], ((W - ctx["handle"].width) // 2, H - 90))
        out = rgba.convert("RGB")
    return out.tobytes()


def _ffmpeg_cmd(spec, total, out):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-"]
    if spec.get("audio"):
        cmd += ["-i", spec["audio"], "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,apad"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono"]
    return cmd + ["-t", f"{total:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
                  "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]


def _context(spec, total):
    outline_img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    draw_room(SD(outline_img), DOOR)
    outline = _downsample(outline_img)
    upper = spec.get("upper", True)
    rng = np.random.default_rng(11)
    return {
        "dark": build_scene(False, outline), "lit": build_scene(True, outline), "beam": build_beam(),
        "door": spec.get("door", [0.4, 1.5]), "walk": spec.get("walk", [1.5, 2.3]), "beam_t": spec["beam_t"],
        "intro": [(c["t0"], c["t1"], c.get("mood", "happy"), _text_layer(c["text"], BOLD, 36, 440))
                  for c in spec.get("intro", [])],
        "lines": [(c["t0"], c["t1"], _text_layer(c["text"].upper() if upper else c["text"], HAND, 74, 900,
                                                  tilt=-1.4 if i % 2 else 1.2))
                  for i, c in enumerate(spec["lines"])],
        "handle": _text_layer(spec["handle"], BOLD, 22, 400) if spec.get("handle") else None,
        "grain": [_grain(rng) for _ in range(3)], "total": total,
    }


def render(spec: dict, out: Path) -> None:
    total = max(c["t1"] for c in spec["lines"]) + 1.0
    ctx = _context(spec, total)
    proc = subprocess.Popen(_ffmpeg_cmd(spec, total, out), stdin=subprocess.PIPE)
    try:
        for n in range(int(total * FPS)):
            t = n / FPS
            proc.stdin.write(_finish(_compose(t, ctx), t, ctx))
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed with exit code {rc}")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    render(json.loads(Path(argv[1]).read_text(encoding="utf-8")), Path(argv[2]))
    print(json.dumps({"video": argv[2]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
