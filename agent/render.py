"""ffmpeg montaj: sahnalar + ovoz + musiqa (ducking) + karaoke subtitr + progress bar."""
import random
from pathlib import Path

from PIL import ImageFont

from .fx import END_SECS, build_sfx, log_fx, sfx_events, video_fx
from .looks import BARS, GRADES, fix_look
from .subtitles import build_ass
from .utils import ROOT, ffprobe_duration, log, run

FALLBACK_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

GRADIENTS = [
    ("0x0f2027", "0x203a43", "0x2c5364"),
    ("0x1a1a2e", "0x16213e", "0x0f3460"),
    ("0x232526", "0x414345", "0x1c1c1c"),
    ("0x3a1c71", "0x1f1c2c", "0x0b0b0f"),
]


def _font(cfg: dict) -> tuple[str, Path]:
    candidates = [ROOT / cfg["subtitles"]["font_file"]] + [Path(p) for p in FALLBACK_FONTS]
    for p in candidates:
        if p.exists():
            family, _style = ImageFont.truetype(str(p), 20).getname()
            return family, p.parent
    raise RuntimeError("Shrift topilmadi — assets/fonts ga .ttf qo'ying")


def scene_timings(scenes: list[dict], words: list[dict], total: float) -> list[tuple[float, float]]:
    """Har sahnaning [start, end] vaqti — so'z vaqtlariga qarab."""
    counts = [len(s["text"].split()) for s in scenes]
    idx, starts = 0, []
    for c in counts:
        starts.append(words[min(idx, len(words) - 1)]["start"] if idx < len(words) else total)
        idx += c
    starts[0] = 0.0
    spans = []
    for i, st in enumerate(starts):
        en = starts[i + 1] if i + 1 < len(starts) else total
        spans.append((st, max(en, st + 0.8)))
    # ketma-ketlikni tekislash
    fixed, cur = [], 0.0
    for st, en in spans:
        d = max(en - max(st, cur), 0.8)
        fixed.append((cur, cur + d))
        cur += d
    scale = total / cur
    return [(a * scale, b * scale) for a, b in fixed]


XFADE_T = 0.35  # sahna o'tishi davomiyligi (soniya)
XFADE_MID = XFADE_T / 2


def _prep_scene(src: Path | None, dur: float, cfg: dict, out: Path, grade: str = "natural"):
    v = cfg["video"]
    W, H, fps = v["width"], v["height"], v["fps"]
    # Klipning o'z harakati saqlanadi: faqat 9:16 ga markazdan kesamiz (sun'iy "pan" yo'q)
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
          f"crop={W}:{H},setsar=1,fps={fps},"
          f"{GRADES.get(grade, GRADES['natural'])},format=yuv420p")
    if src is None:
        c0, c1, c2 = random.choice(GRADIENTS)
        inp = ["-f", "lavfi", "-i",
               f"gradients=s={W}x{H}:c0={c0}:c1={c1}:c2={c2}:n=3:speed=0.015:r={fps}"]
    else:
        # Klip boshidagi harakatsiz qismni tashlab, tasodifiy joydan boshlaymiz
        start = 0.0
        try:
            clip_dur = ffprobe_duration(src)
            if clip_dur > dur + 1.5:
                start = random.uniform(0.5, clip_dur - dur - 0.5)
        except Exception:  # noqa: BLE001
            pass
        inp = ["-ss", f"{start:.2f}", "-stream_loop", "-1", "-i", str(src)]
    run(["ffmpeg", "-y", "-hide_banner", *inp, "-t", f"{dur:.3f}", "-an",
         "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-r", str(fps), str(out)])


def _join(parts: list[Path], spans: list[tuple[float, float]], transition: str, out: Path):
    """Sahnalarni ulash: oddiy kesish (concat) yoki xfade o'tishlari bilan."""
    if transition == "cut" or len(parts) < 2:
        lst = out.parent / "list.txt"
        lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
        return
    # Har sahna (oxirgisidan tashqari) XFADE_T ga uzunroq yasalgan, shuning uchun umumiy uzunlik
    # va sahna chegaralari ovoz bilan mos qoladi: o'tish aynan chegarada boshlanadi.
    inputs, chain, prev, acc = [], [], "[0:v]", 0.0
    for p in parts:
        inputs += ["-i", str(p)]
    for i in range(1, len(parts)):
        acc += spans[i - 1][1] - spans[i - 1][0]
        lbl = f"[x{i}]"
        chain.append(f"{prev}[{i}:v]xfade=transition={transition}:duration={XFADE_T}:offset={acc:.3f}{lbl}")
        prev = lbl
    run(["ffmpeg", "-y", "-hide_banner", *inputs, "-filter_complex", ";".join(chain),
         "-map", prev, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", str(out)])


def _has_fx(look: dict) -> bool:
    return any(look.get(k) for k in ("sound", "entrance", "texture", "ending"))


def _final(joined: Path, voice_mp3: Path, music: Path | None, ass: Path, font_dir: Path, cfg: dict,
           total: float, look: dict, centers: list[float], hook_secs: float, workdir: Path,
           out_mp4: Path, fx_on: bool) -> None:
    v = cfg["video"]
    W, H = v["width"], v["height"]
    bar = BARS.get(look.get("bar", "bottom"), ("bottom", 14))
    has_bar = bool(v.get("progress_bar") and bar)
    ending = fx_on and look.get("ending") == "zoom" and has_bar  # loop kanallarda (bar yo'q) o'chiq

    inputs = ["-i", str(joined), "-i", str(voice_mp3)]
    next_idx = 2
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        next_idx += 1

    sfx_idx = None
    if fx_on and look.get("sound"):
        try:
            sfx = build_sfx(workdir, total, sfx_events(look["sound"], centers, hook_secs), voice_mp3)
        except Exception as e:  # noqa: BLE001 — ovoz effekti bo'lmasa ham video chiqsin
            log.warning("SFX yasalmadi, ovozsiz davom: %s", e)
            sfx = None
        if sfx:
            inputs += ["-i", str(sfx)]
            sfx_idx = next_idx
            next_idx += 1

    fx_inputs, fx_graph, vsrc = [], "", "[0:v]"
    if fx_on:
        fx_inputs, fx_graph, vsrc = video_fx(look, total, centers, workdir, W, H, next_idx, ending)
        inputs += fx_inputs
        log_fx(look)

    ass_esc = str(ass).replace("\\", "/").replace(":", "\\:")
    fdir_esc = str(font_dir).replace("\\", "/").replace(":", "\\:")
    vchain = f"{vsrc}ass='{ass_esc}':fontsdir='{fdir_esc}'"
    if has_bar:
        where, bh = bar
        by = "0" if where == "top" else f"ih-{bh}"
        fill = f"min(t/{max(total - END_SECS, 1.0):.3f},1)" if ending else f"t/{total:.3f}"
        vchain += (f",drawbox=x=0:y={by}:w='iw*{fill}':h={bh}:"
                   f"color={v['progress_color']}@0.95:t=fill")
    vchain += "[v]"
    if fx_graph:
        vchain = fx_graph + ";" + vchain

    fade_st = max(total - 0.6, 0)
    tail = f"loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st={fade_st:.2f}:d=0.6[a]"
    vo = f"[1:a]aresample=48000,apad=whole_dur={total:.3f}"
    sx = f";[{sfx_idx}:a]aresample=48000[sx]" if sfx_idx else ""
    if music:
        n = 3 if sfx_idx else 2
        achain = (
            f"{vo},asplit=2[vo][sc];"
            f"[2:a]aresample=48000,volume={cfg['music']['volume']},afade=t=in:d=1[m];"
            f"[m][sc]sidechaincompress=threshold=0.03:ratio=8:attack=15:release=350[md]{sx};"
            f"[vo][md]{'[sx]' if sfx_idx else ''}amix=inputs={n}:duration=first:normalize=0,{tail}"
        )
    elif sfx_idx:
        achain = f"{vo}[vo]{sx};[vo][sx]amix=inputs=2:duration=first:normalize=0,{tail}"
    else:
        achain = f"{vo},{tail}"

    log.info("Yakuniy render (%.1fs)%s...", total, " + FX" if fx_on else "")
    run(["ffmpeg", "-y", "-hide_banner", *inputs,
         "-filter_complex", f"{vchain};{achain}",
         "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
         "-c:v", "libx264", "-preset", v["preset"], "-crf", str(v["crf"]),
         "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(v["fps"]),
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", str(out_mp4)])


def render(story: dict, clips: list, voice_mp3: Path, words: list[dict], audio_dur: float,
           cfg: dict, workdir: Path, out_mp4: Path, look: dict | None = None) -> Path:
    look = look or {}
    v = cfg["video"]
    max_d = v["max_duration"]

    # 1) Agar ovoz juda uzun bo'lsa — tezlatamiz (Shorts chegarasiga sig'dirish)
    tempo = 1.0
    if audio_dur + 0.7 > max_d:
        tempo = min((audio_dur + 0.7) / max_d, 1.25)
        log.warning("Ovoz uzun (%.1fs) — %.2fx tezlashtiriladi", audio_dur, tempo)
        fast = workdir / "voice_fast.mp3"
        run(["ffmpeg", "-y", "-i", str(voice_mp3), "-filter:a", f"atempo={tempo:.4f}", str(fast)])
        voice_mp3 = fast
        words = [{**w, "start": w["start"] / tempo, "end": w["end"] / tempo} for w in words]
        audio_dur = ffprobe_duration(fast)
    total = min(audio_dur + 0.7, max_d)

    # 2) Sahnalar
    spans = scene_timings(story["scenes"], words, total)
    transition = look.get("transition", "cut")
    log.info("Ko'rinish: %s", ", ".join(f"{k}={v_}" for k, v_ in look.items()) or "standart")
    parts = []
    for i, ((a, b), clip) in enumerate(zip(spans, clips)):
        p = workdir / f"scene_{i:02d}.mp4"
        extra = XFADE_T if transition != "cut" and i + 1 < len(spans) else 0.0
        _prep_scene(clip, b - a + extra, cfg, p, look.get("grade", "natural"))
        parts.append(p)
    joined = workdir / "joined.mp4"
    try:
        _join(parts, spans, transition, joined)
    except Exception as e:  # noqa: BLE001 — o'tish ishlamasa ham video chiqsin
        log.warning("O'tish (%s) ishlamadi, oddiy kesish: %s", transition, e)
        for i, ((a, b), clip) in enumerate(zip(spans, clips)):
            _prep_scene(clip, b - a, cfg, parts[i], look.get("grade", "natural"))
        _join(parts, spans, "cut", joined)

    # 3) Subtitr
    font_name, font_dir = _font(cfg)
    ass = build_ass(words, story.get("hook", ""), total, font_name, cfg, workdir / "subs.ass", look)

    # 4) Yakuniy montaj
    music = None
    if cfg["music"]["enabled"]:
        mdir = ROOT / cfg["music"]["folder"]
        tracks = sorted(mdir.glob("*.mp3")) + sorted(mdir.glob("*.m4a"))
        if tracks:
            music = random.choice(tracks)
            log.info("Musiqa: %s", music.name)

    hook_secs = cfg["subtitles"]["hook_seconds"]
    centers = [b_ + (XFADE_MID if transition != "cut" else 0.0) for (_a, b_) in spans[:-1]]
    look = fix_look(dict(look))
    attempts = [True, False] if _has_fx(look) else [False]
    for fx_on in attempts:
        try:
            _final(joined, voice_mp3, music, ass, font_dir, cfg, total, look, centers, hook_secs,
                   workdir, out_mp4, fx_on)
            break
        except Exception as e:  # effekt ishlamasa oddiy render
            if not fx_on:
                raise
            log.warning("Premium effektlar ishlamadi, oddiy render: %s", e)
    log.info("Video tayyor: %s (%.1f MB)", out_mp4.name, out_mp4.stat().st_size / 1e6)
    return out_mp4
