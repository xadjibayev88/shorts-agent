"""Har video boshqacha ko'rinsin: rang, sahna o'tishi, subtitr joyi va animatsiyasi, hook uslubi, progress bar.

Brend qoidasi o'zgarmaydi: subtitr qatorda 3 so'z, to'liq oq (#FFFFFF), qora kontur, rangli belgilash yo'q.
Har uslub o'qi alohida tanlanadi va oxirgi bir necha videoda ishlatilgani qaytarilmaydi,
shuning uchun ketma-ket ikki video bir xil chiqmaydi. Tanlov history["looks"] ga yoziladi.
"""
import random

# Rang (ffmpeg filtrlari, kesib olingan 9:16 kadrga qo'llanadi)
GRADES = {
    "natural": "eq=contrast=1.05:saturation=1.1",
    "warm": "colorbalance=rs=0.06:gs=0.01:bs=-0.06:rm=0.04:bm=-0.04,eq=contrast=1.06:saturation=1.12",
    "cool": "colorbalance=rs=-0.05:bs=0.07:rm=-0.03:bm=0.05,eq=contrast=1.06:saturation=1.0",
    "teal_orange": "colorbalance=rs=-0.08:bs=0.08:rh=0.08:bh=-0.08,eq=contrast=1.1:saturation=1.15",
    "moody": "eq=contrast=1.14:brightness=-0.035:saturation=0.85,vignette=PI/5",
    "vivid": "eq=contrast=1.08:saturation=1.32",
    "film": "curves=preset=lighter,eq=contrast=1.08:saturation=0.92,noise=alls=7:allf=t,vignette=PI/6",
}

# Sahnalar orasidagi o'tish (ffmpeg xfade). "cut" = oddiy kesish.
TRANSITIONS = ["cut", "fade", "dissolve", "slideup", "smoothleft", "circleopen",
               "wipeup", "zoomin", "fadeblack", "radial", "hblur", "smoothup"]

# Subtitr: markaz y (px), shrift o'lchami, so'z animatsiyasi, faol so'z effekti
CAPTIONS = {
    "center_pop":   {"y": 1150, "size": 92,  "anim": "pop",   "active": "scale"},
    "middle_rise":  {"y": 980,  "size": 96,  "anim": "rise",  "active": "scale"},
    "lower_fade":   {"y": 1320, "size": 86,  "anim": "fade",  "active": "scale"},
    "upper_bounce": {"y": 820,  "size": 100, "anim": "bounce", "active": "none"},
    "low_slide":    {"y": 1420, "size": 84,  "anim": "slide", "active": "scale"},
    "center_shadow": {"y": 1100, "size": 94, "anim": "fade",  "active": "underline"},
}

# Hook (ekran tepasidagi yozuv)
HOOKS = ["white_box", "black_box", "outline_big", "middle_zoom", "top_slide"]

# Progress bar: (joy, qalinlik) yoki None
BARS = {"bottom": ("bottom", 14), "top": ("top", 10), "thin": ("bottom", 6), "none": None}

AXES = {"grade": list(GRADES), "transition": TRANSITIONS, "caption": list(CAPTIONS),
        "hook": HOOKS, "bar": list(BARS)}
AVOID_LAST = {"grade": 3, "transition": 4, "caption": 3, "hook": 2, "bar": 1}


def pick_look(history: dict, rng: random.Random | None = None) -> dict:
    """Har o'q bo'yicha oxirgi videolarda bo'lmagan variantni tanlaydi."""
    rng = rng or random.Random()
    past = history.get("looks", [])
    look = {}
    for axis, options in AXES.items():
        recent = {p.get(axis) for p in past[-AVOID_LAST[axis]:]}
        pool = [o for o in options if o not in recent] or options
        look[axis] = rng.choice(pool)
    # O'rtadagi katta hook yuqoridagi subtitr bilan ustma-ust tushmasin
    if look["hook"] == "middle_zoom" and CAPTIONS[look["caption"]]["y"] < 1000:
        look["caption"] = rng.choice([c for c, v in CAPTIONS.items() if v["y"] >= 1000])
    return look


def remember(history: dict, look: dict, keep: int = 40) -> None:
    history["looks"] = (history.get("looks", []) + [look])[-keep:]
