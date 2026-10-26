"""Karaoke uslubidagi (so'z-so'z yonadigan) ASS subtitrlar + tepadagi HOOK."""
from pathlib import Path


def _ts(sec: float) -> str:
    sec = max(sec, 0)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _clean(w: str) -> str:
    return w.replace("{", "(").replace("}", ")").replace("\\", "/")


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


def build_ass(words: list[dict], hook: str, total: float, font_name: str, cfg: dict, out: Path):
    s = cfg["subtitles"]
    W, H = cfg["video"]["width"], cfg["video"]["height"]
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{font_name},{s['font_size']},{s['base_color']},&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,1,0,1,{s['outline']},3,5,60,60,0,1
Style: Hook,{font_name},74,&H00000000,&H000000FF,&H0000D4FF,&H0000D4FF,-1,0,0,0,100,100,1,0,3,18,0,8,80,80,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    hi = s["highlight_color"]
    base = s["base_color"]
    x, y = W // 2, s["position_y"]

    groups = _groups(words, s["words_per_line"])
    for gi, g in enumerate(groups):
        g_end = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else total
        g_end = min(g_end, g[-1]["end"] + 0.6)  # pauzada ekran bo'shab qolsin
        for k, w in enumerate(g):
            start = w["start"]
            end = g[k + 1]["start"] if k + 1 < len(g) else g_end
            if end <= start:
                continue
            parts = []
            for j, ww in enumerate(g):
                txt = _clean(ww["word"].upper())
                if j == k:
                    parts.append(f"{{\\c{hi}\\fscx108\\fscy108}}{txt}{{\\c{base}\\fscx100\\fscy100}}")
                else:
                    parts.append(txt)
            pop = "\\fscx80\\fscy80\\t(0,90,\\fscx100\\fscy100)" if k == 0 else ""
            text = f"{{\\pos({x},{y}){pop}}}" + " ".join(parts)
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Sub,,0,0,0,,{text}")

    if hook:
        hs = cfg["subtitles"]["hook_seconds"]
        lines.append(
            f"Dialogue: 1,{_ts(0)},{_ts(hs)},Hook,,0,0,0,,"
            f"{{\\fad(120,200)\\fscx85\\fscy85\\t(0,140,\\fscx100\\fscy100)}}{_clean(hook.upper())}"
        )

    out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return out
