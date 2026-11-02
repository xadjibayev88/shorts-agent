"""Hand-drawn look for the lyric-toon scene: anti-aliased, slightly wobbly marker strokes
that re-jitter a few times per second ("boil"), plus the characters and props.

Everything is drawn through SD, which supersamples (draws at S x size and the caller
downsamples), so lines come out smooth instead of jagged.
"""
from __future__ import annotations

import math
import random

from PIL import ImageDraw

INK = (14, 14, 18)
YELLOW = (250, 236, 110)
PALE = (222, 222, 228)
LW = 9
SS = 2  # supersampling factor
BOIL_FPS = 8


class SD:
    """Scaled drawing surface: takes scene coordinates, draws at SS x into `img`."""

    def __init__(self, img, ox=0, oy=0, boil=0, s=SS):
        self.d, self.ox, self.oy, self.s, self.boil, self.k = ImageDraw.Draw(img), ox, oy, s, boil, 0

    def rng(self):
        self.k += 1
        return random.Random(self.boil * 100003 + self.k)

    def p(self, pt):
        return ((pt[0] - self.ox) * self.s, (pt[1] - self.oy) * self.s)

    def box(self, b):
        return [*self.p(b[:2]), *self.p(b[2:])]

    def line(self, pts, w=LW, fill=INK):
        sp = [self.p(q) for q in pts]
        self.d.line(sp, fill=fill, width=int(w * self.s), joint="curve")
        r = w * self.s / 2
        for x, y in (sp[0], sp[-1]):  # round caps
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

    def ellipse(self, b, fill=None, outline=None, w=LW):
        self.d.ellipse(self.box(b), fill=fill, outline=outline, width=int(w * self.s))

    def rect(self, b, fill=None, outline=None, w=LW, r=0):
        if r:
            self.d.rounded_rectangle(self.box(b), r * self.s, fill=fill, outline=outline, width=int(w * self.s))
        else:
            self.d.rectangle(self.box(b), fill=fill, outline=outline, width=int(w * self.s))

    def poly(self, pts, fill=None, outline=None, w=LW):
        self.d.polygon([self.p(q) for q in pts], fill=fill, outline=outline, width=int(w * self.s))

    def arc(self, b, a0, a1, w=LW, fill=INK):
        self.d.arc(self.box(b), a0, a1, fill=fill, width=int(w * self.s))


def stroke(sd: SD, a, b, w=LW, amp=1.8):
    """Marker stroke from a to b with a gentle hand wobble."""
    dist = math.dist(a, b)
    n = max(2, int(dist / 45) + 1)
    nx, ny = (-(b[1] - a[1]) / (dist or 1), (b[0] - a[0]) / (dist or 1))
    rng, pts = sd.rng(), []
    for i in range(n + 1):
        t = i / n
        j = rng.uniform(-amp, amp) if 0 < i < n else rng.uniform(-amp / 2, amp / 2)
        pts.append((a[0] + (b[0] - a[0]) * t + nx * j, a[1] + (b[1] - a[1]) * t + ny * j))
    sd.line(pts, w)


def blob(sd: SD, cx, cy, r, fill, w=LW, amp=1.6):
    """Slightly irregular circle (a hand-drawn head)."""
    rng, pts = sd.rng(), []
    for i in range(24):
        a = i / 24 * 2 * math.pi
        rr = r + rng.uniform(-amp, amp)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    sd.poly(pts, fill=fill)
    sd.line(pts + [pts[0], pts[1]], w)


def _face(sd, cx, cy, mood):
    for dx in (-17, 17):
        sd.line([(cx + dx, cy - 4), (cx + dx, cy + 6)], 7)
    if mood == "happy":
        sd.arc([cx - 24, cy + 6, cx + 24, cy + 34], 15, 165, 6)
        return
    sd.arc([cx - 22, cy + 22, cx + 22, cy + 46], 195, 345, 6)
    sd.line([(cx - 30, cy - 18), (cx - 8, cy - 11)], 5)  # worried brows
    sd.line([(cx + 30, cy - 18), (cx + 8, cy - 11)], 5)


def draw_man(sd: SD, t, mood="happy", dx=0):
    """Man in a hat with a cigarette and a mug. mood: happy | sad."""
    cx, top = 445 + dx, 640
    sway = math.sin(t * 2.4) * 9
    breathe = math.sin(t * 1.6) * 2
    blob(sd, cx, top, 48, YELLOW)
    sd.ellipse([cx - 86, top - 58, cx + 86, top - 22], fill=INK)  # brim
    sd.rect([cx - 48, top - 116, cx + 48, top - 44], fill=INK, r=10)  # crown
    sd.rect([cx - 48, top - 72, cx + 48, top - 58], fill=(110, 110, 120))  # band
    _face(sd, cx, top, mood)
    sx, sy = cx + 42, top + 26  # cigarette and smoke
    stroke(sd, (sx, sy), (sx + 38, sy - 14), 7)
    for i in range(3):
        px = sx + 48 + math.sin(t * 3 + i) * 8
        sd.line([(px, sy - 28 - i * 24), (px + 10, sy - 50 - i * 24)], 4)
    stroke(sd, (cx, top + 48), (cx, top + 252 + breathe))  # body
    for hip, foot in (((cx - 46, top + 446), (cx - 70, top + 452)), ((cx + 42, top + 446), (cx + 68, top + 452))):
        stroke(sd, (cx, top + 252 + breathe), hip)
        stroke(sd, hip, foot, 8)  # shoes
    stroke(sd, (cx, top + 104), (cx - 74, top + 196))  # relaxed arm
    hand = (cx + 98, top + 168 + sway)
    stroke(sd, (cx, top + 104), hand)
    sd.rect([hand[0] - 6, hand[1] - 4, hand[0] + 52, hand[1] + 46], fill=INK, r=7)  # mug
    sd.arc([hand[0] + 40, hand[1] + 6, hand[0] + 72, hand[1] + 34], 270, 90, 5)  # handle


def draw_lying(sd: SD, t):
    """Tired figure on the floor: headphones, laptop, phones and papers; head bobs slowly."""
    cx, cy = 390, 1590
    bob = math.sin(t * 2 * math.pi) * 5
    blob(sd, cx, cy + bob, 44, PALE)
    sd.arc([cx - 58, cy - 58 + bob, cx + 58, cy + 30 + bob], 180, 360, 9)  # headphone band
    sd.ellipse([cx - 62, cy - 14 + bob, cx - 40, cy + 20 + bob], fill=INK)
    for ex in (-9, 15):
        sd.line([(cx + ex, cy - 4 + bob), (cx + ex, cy + 5 + bob)], 6)
    sd.arc([cx - 12, cy + 12 + bob, cx + 22, cy + 28 + bob], 190, 350, 5)
    stroke(sd, (cx + 44, cy + 8), (cx + 210, cy + 32), 8)  # torso
    stroke(sd, (cx + 210, cy + 32), (cx + 300, cy + 118), 8)  # legs
    stroke(sd, (cx + 210, cy + 32), (cx + 322, cy + 72), 8)
    stroke(sd, (cx + 84, cy + 18), (cx + 146, cy - 26), 8)  # arm to laptop
    lx, ly = cx + 172, cy - 92
    sd.poly([(lx, ly + 72), (lx + 108, ly + 72), (lx + 122, ly), (lx + 16, ly)], outline=INK, w=6)
    sd.line([(lx - 8, ly + 80), (lx + 124, ly + 80)], 6)
    for px, py, r in ((cx - 240, cy + 10, 7), (cx - 175, cy + 100, -10), (cx + 10, cy + 144, 5),
                      (cx + 270, cy + 154, -5), (cx - 260, cy + 138, 9), (cx + 120, cy + 120, -6)):
        sd.poly([(px, py), (px + 60, py - r), (px + 66, py + 44), (px + 5, py + 48)], outline=INK, w=5)
    sd.rect([cx + 56, cy + 92, cx + 90, cy + 146], outline=INK, w=5, r=6)  # phone
    sd.rect([cx - 120, cy + 96, cx - 86, cy + 150], outline=INK, w=5, r=6)


def draw_room(sd: SD, door, lit_outline=True):
    """Outline layer of the room: door frame, floor and wall lines, window, ceiling cord."""
    x0, y0, x1, y1 = door
    for a, b in (((x1, y0), (x1 + 280, y0 + 100)), ((x1 + 280, y0 + 100), (x1 + 280, y1 + 90)),
                 ((x1 + 280, y1 + 90), (x1, y1)), ((x0, y0), (x1, y0)), ((x0, y0), (x0, y1)),
                 ((0, y1 + 50), (x0, y1)), ((x0, y1), (x1, y1)), ((x1, y1), (1080, y1 + 360))):
        stroke(sd, a, b, LW, 1.2)
    wx, wy = 900, 520
    sd.rect([wx, wy, wx + 80, wy + 90], outline=INK, w=7)
    sd.line([(wx + 40, wy), (wx + 40, wy + 90)], 6)
    sd.line([(wx, wy + 45), (wx + 80, wy + 45)], 6)
    sd.line([(735, 0), (735, 420)], 6)
    sd.ellipse([724, 420, 746, 442], fill=INK)
