"""Karaoke uslubidagi (so'z-so'z yonadigan) ASS subtitrlar + tepadagi HOOK.

Joyi, o'lchami, animatsiyasi va hook ko'rinishi har videoda boshqacha (agent/looks.py),
rangi esa doim brend bo'yicha: oq matn, qora kontur.
"""
from pathlib import Path

from .looks import CAPTIONS


def _ts(sec: float) -> str:
    sec = max(sec, 0)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _clean(w: str) -> str:
    return w.replace("{", "(").replace("}", ")").replace("\\", "/")


# O'zbekcha son so'zlari (apostrof variantlari _norm da tekislanadi)
NUMBER_WORDS = {
    "bir", "ikki", "uch", "to'rt", "besh", "olti", "yetti", "sakkiz", "to'qqiz", "o'n",
    "yigirma", "o'ttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "to'qson",
    "yuz", "ming", "million", "milliard", "trillion", "foiz", "yarim",
}
# "bir" juda ko'p ishlatiladi ("bir kuni"): faqat boshqa son so'z yonida bo'lsa pop bo'ladi
WEAK_NUMBER_WORDS = {"bir", "yarim"}
POP_MIN_GAP = 0.6  # ikki pop orasidagi eng kam masofa (s)
# ASS: (cho'qqi %, tinch holat %, oshish ms, tushish ms). Rang o'zgarmaydi (brend qoidasi).
POP_STYLES = {"pop": (132, 112, 90, 170), "spring": (146, 108, 70, 230)}


def _norm(w: str) -> str:
    w = w.lower()
    for ch in "’ʻʼ‘`´":
        w = w.replace(ch, "'")
    return w.strip(".,!?…:;\"«»()-–—")


def _number_flags(words: list[dict]) -> list[bool]:
    """Qaysi so'zlar raqam/son (raqamli yoki so'z bilan) — pop uchun."""
    toks = [_norm(w["word"]) for w in words]
    flags, last_t = [], -9.0
    for i, t in enumerate(toks):
        strong = any(c.isdigit() for c in t) or (t in NUMBER_WORDS and t not in WEAK_NUMBER_WORDS)
        weak = t in WEAK_NUMBER_WORDS and (
            (i + 1 < len(toks) and toks[i + 1] in NUMBER_WORDS) or (i > 0 and toks[i - 1] in NUMBER_WORDS))
        hit = (strong or weak) and words[i]["start"] - last_t >= POP_MIN_GAP
        if hit:
            last_t = words[i]["start"]
        flags.append(hit)
    return flags


def _line_chars(group: list[dict], lo: int, hi: int) -> int:
    return sum(len(w["word"]) for w in group[lo:hi]) + (hi - lo - 1)


def _group_break(group: list[dict], size: int) -> int | None:
    """Pop bor qator 1 qatorga sig'masa, barcha hodisalarda bir xil joyda aniq \\N bilan bo'linadi."""
    if len(group) < 2 or _line_chars(group, 0, len(group)) * CHAR_W * size <= LINE_LIMIT_PX:
        return None
    return min(range(1, len(group)), key=lambda i: max(_line_chars(group, 0, i), _line_chars(group, i, len(group))))


def _pop_peak(peak: int, group: list[dict], k: int, size: int, brk: int | None) -> int:
    """Pop paytida satr kengligi LINE_LIMIT_PX dan oshmasligi uchun cho'qqini cheklaydi (100 dan past emas)."""
    lo, hi = (0, len(group)) if brk is None else ((0, brk) if k < brk else (brk, len(group)))
    word_w = len(group[k]["word"]) * CHAR_W * size
    others = (_line_chars(group, lo, hi) - len(group[k]["word"])) * CHAR_W * size
    room = (LINE_LIMIT_PX - others) / max(word_w, 1) * 100
    return int(max(100, min(peak, room)))


def _groups(words: list[dict], per_line: int) -> list[list[dict]]:
    groups, cur = [], []
    for w in words:
        cur.append(w)
        ends_sentence = w["word"][-1:] in ".!?…:;"
        if len(cur) >= per_line or ends_sentence:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


# Hook uslublari: (ASS style qatori, matn oldidagi teglar). {x} {top} — joy.
HOOK_BASE = {"black_box": 92, "outline_big": 96, "middle_zoom": 110, "top_slide": 92, "white_box": 92}
HOOK_MIN = 54
CHAR_W = 0.72           # qalin katta harf o'rtacha kengligi / shrift o'lchami (taxmin)
LINE_LIMIT_PX = 940     # subtitr qatori shu kenglikdan oshmasin
HOOK_AVAIL_PX = 860     # hook matni uchun (chetlar va quti ichki bo'shlig'i chiqarilgan)


def _hook_lines(hook: str) -> list[str]:
    """Hook matnini ko'pi bilan 2 ta muvozanatli qatorga bo'ladi (aniq \\N, animatsiya paytida o'ralmaydi)."""
    words = hook.split()
    if len(words) < 2 or len(hook) <= 14:
        return [hook]
    best = min(range(1, len(words)), key=lambda i: max(len(" ".join(words[:i])), len(" ".join(words[i:]))))
    return [" ".join(words[:best]), " ".join(words[best:])]


def _hook_size(kind: str, lines: list[str]) -> int:
    """Eng uzun qator HOOK_AVAIL_PX ga sig'adigan eng katta o'lcham (taxminiy kenglik bo'yicha)."""
    size = HOOK_BASE.get(kind, 92)
    longest = max(len(ln) for ln in lines) if lines else 1
    while size > HOOK_MIN and longest * CHAR_W * size > HOOK_AVAIL_PX:
        size -= 2
    return size


def _hook_style(kind: str, font: str, size: int = 92) -> tuple[str, str]:
    if kind == "black_box":
        return (f"Style: Hook,{font},{size},&H00FFFFFF,&H000000FF,&H20000000,&H20000000,-1,0,0,0,100,100,1,0,3,18,0,8,80,80,260,1",
                "\\fad(120,200)\\fscx85\\fscy85\\t(0,140,\\fscx100\\fscy100)")
    if kind == "outline_big":
        return (f"Style: Hook,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,8,4,8,70,70,250,1",
                "\\fad(100,200)\\fscx70\\fscy70\\t(0,160,\\fscx100\\fscy100)")
    if kind == "middle_zoom":
        return (f"Style: Hook,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,9,4,5,70,70,0,1",
                "\\pos({x},560)\\fad(80,220)\\fscx55\\fscy55\\t(0,220,\\fscx100\\fscy100)")
    if kind == "top_slide":
        return (f"Style: Hook,{font},{size},&H00000000,&H000000FF,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,1,0,3,18,0,8,80,80,260,1",
                "\\move({x},120,{x},{top},0,200)\\fad(0,200)")
    # white_box (asl uslub)
    return (f"Style: Hook,{font},{size},&H00000000,&H000000FF,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,1,0,3,18,0,8,80,80,260,1",
            "\\fad(120,200)\\fscx85\\fscy85\\t(0,140,\\fscx100\\fscy100)")


def _enter(anim: str, x: int, y: int) -> str:
    """Yangi qator paydo bo'lish animatsiyasi (faqat qatorning 1-so'zida)."""
    return {
        "pop": f"\\pos({x},{y})\\fscx80\\fscy80\\t(0,90,\\fscx100\\fscy100)",
        "rise": f"\\move({x},{y + 45},{x},{y},0,130)\\fad(90,0)",
        "fade": f"\\pos({x},{y})\\fad(110,0)",
        "bounce": f"\\pos({x},{y})\\fscx122\\fscy122\\t(0,80,\\fscx94\\fscy94)\\t(80,160,\\fscx100\\fscy100)",
        "slide": f"\\move({x - 70},{y},{x},{y},0,120)\\fad(80,0)",
    }.get(anim, f"\\pos({x},{y})")


def build_ass(words: list[dict], hook: str, total: float, font_name: str, cfg: dict, out: Path,
              look: dict | None = None):
    s = cfg["subtitles"]
    W, H = cfg["video"]["width"], cfg["video"]["height"]
    look = look or {}
    cap = CAPTIONS.get(look.get("caption"), {"y": s["position_y"], "size": s["font_size"],
                                             "anim": "pop", "active": "scale"})
    hook_lines = _hook_lines(_clean(hook.upper()))
    hook_kind = look.get("hook", "white_box")
    hook_style, hook_tags = _hook_style(hook_kind, font_name, _hook_size(hook_kind, hook_lines))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{font_name},{cap['size']},{s['base_color']},&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,1,0,1,{s['outline']},3,5,60,60,0,1
{hook_style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    hi = s["highlight_color"]
    base = s["base_color"]
    x, y = W // 2, cap["y"]

    pop = POP_STYLES.get(look.get("emphasis"))
    pop_ids = {id(w) for w, f in zip(words, _number_flags(words)) if f} if pop else set()
    groups = _groups(words, s["words_per_line"])
    for gi, g in enumerate(groups):
        g_end = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else total
        g_end = min(g_end, g[-1]["end"] + 0.6)  # pauzada ekran bo'shab qolsin
        has_pop = any(id(ww) in pop_ids for ww in g)
        brk = _group_break(g, cap["size"]) if has_pop else None
        for k, w in enumerate(g):
            start = w["start"]
            end = g[k + 1]["start"] if k + 1 < len(g) else g_end
            if end <= start:
                continue
            parts = []
            for j, ww in enumerate(g):
                txt = _clean(ww["word"].upper())
                if j == k and id(ww) in pop_ids:
                    peak, rest, up, down = pop
                    peak = _pop_peak(peak, g, k, cap["size"], brk)
                    rest = min(rest, peak)
                    parts.append(f"{{\\fscx100\\fscy100\\t(0,{up},\\fscx{peak}\\fscy{peak})"
                                 f"\\t({up},{up + down},\\fscx{rest}\\fscy{rest})}}{txt}"
                                 f"{{\\fscx100\\fscy100}}")
                elif j == k and cap["active"] == "scale":
                    parts.append(f"{{\\c{hi}\\fscx108\\fscy108}}{txt}{{\\c{base}\\fscx100\\fscy100}}")
                elif j == k and cap["active"] == "underline":
                    parts.append(f"{{\\u1}}{txt}{{\\u0}}")
                else:
                    parts.append(txt)
            tags = _enter(cap["anim"], x, y) if k == 0 else f"\\pos({x},{y})"
            if has_pop:
                # pop bor qatorning barcha hodisalarida bir xil: qayta o'ralmasin, sakramasin
                tags += "\\q2"
            if brk is None:
                body = " ".join(parts)
            else:
                body = " ".join(parts[:brk]) + "\\N" + " ".join(parts[brk:])
            text = "{" + tags + "}" + body
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Sub,,0,0,0,,{text}")

    if hook:
        hs = cfg["subtitles"]["hook_seconds"]
        lines.append(
            f"Dialogue: 1,{_ts(0)},{_ts(hs)},Hook,,0,0,0,,"
            "{" + hook_tags.format(x=W // 2, top=260) + "\\q2}" + "\\N".join(hook_lines)
        )

    out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return out
