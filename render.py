"""ffmpeg montaj: sahnalar + ovoz + musiqa (ducking) + karaoke subtitr + progress bar."""
import random
from pathlib import Path

from PIL import ImageFont

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


def _prep_scene(src: Path | None, dur: float, cfg: dict, out: Path):
    v = cfg["video"]
    W, H, fps = v["width"], v["height"], v["fps"]
    # 112% kattalashtirib, sekin "pan" — kadr jonli ko'rinadi
    bw, bh = int(W * 1.12) // 2 * 2, int(H * 1.12) // 2 * 2
    direction = random.choice([1, -1])
    xexpr = f"(iw-ow)*(0.5+{direction}*0.4*(t/{dur:.3f}-0.5))"
    vf = (f"scale={bw}:{bh}:force_original_aspect_ratio=increase,"
          f"crop={W}:{H}:x='{xexpr}':y='(ih-oh)/2',setsar=1,fps={fps},"
          f"eq=brightness=-0.05:contrast=1.06:saturation=1.12,format=yuv420p")
    if src is None:
        c0, c1, c2 = random.choice(GRADIENTS)
        inp = ["-f", "lavfi", "-i",
               f"gradients=s={W}x{H}:c0={c0}:c1={c1}:c2={c2}:n=3:speed=0.015:r={fps}"]
    else:
        inp = ["-stream_loop", "-1", "-i", str(src)]
    run(["ffmpeg", "-y", "-hide_banner", *inp, "-t", f"{dur:.3f}", "-an",
         "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-r", str(fps), str(out)])


def render(story: dict, clips: list, voice_mp3: Path, words: list[dict], audio_dur: float,
           cfg: dict, workdir: Path, out_mp4: Path) -> Path:
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
    parts = []
    for i, ((a, b), clip) in enumerate(zip(spans, clips)):
        p = workdir / f"scene_{i:02d}.mp4"
        _prep_scene(clip, b - a, cfg, p)
        parts.append(p)
    lst = workdir / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    joined = workdir / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])

    # 3) Subtitr
    font_name, font_dir = _font(cfg)
    ass = build_ass(words, story.get("hook", ""), total, font_name, cfg, workdir / "subs.ass")

    # 4) Yakuniy montaj
    music = None
    if cfg["music"]["enabled"]:
        mdir = ROOT / cfg["music"]["folder"]
        tracks = sorted(mdir.glob("*.mp3")) + sorted(mdir.glob("*.m4a"))
        if tracks:
            music = random.choice(tracks)
            log.info("Musiqa: %s", music.name)

    ass_esc = str(ass).replace("\\", "/").replace(":", "\\:")
    fdir_esc = str(font_dir).replace("\\", "/").replace(":", "\\:")
    vchain = f"[0:v]ass='{ass_esc}':fontsdir='{fdir_esc}'"
    if v.get("progress_bar"):
        vchain += (f",drawbox=x=0:y=ih-14:w='iw*t/{total:.3f}':h=14:"
                   f"color={v['progress_color']}@0.95:t=fill")
    vchain += "[v]"

    inputs = ["-i", str(joined), "-i", str(voice_mp3)]
    fade_st = max(total - 0.6, 0)
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        achain = (
            f"[1:a]aresample=48000,apad=whole_dur={total:.3f},asplit=2[vo][sc];"
            f"[2:a]aresample=48000,volume={cfg['music']['volume']},afade=t=in:d=1[m];"
            f"[m][sc]sidechaincompress=threshold=0.03:ratio=8:attack=15:release=350[md];"
            f"[vo][md]amix=inputs=2:duration=first:normalize=0,"
            f"loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st={fade_st:.2f}:d=0.6[a]"
        )
    else:
        achain = (f"[1:a]aresample=48000,apad=whole_dur={total:.3f},"
                  f"loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st={fade_st:.2f}:d=0.6[a]")

    log.info("Yakuniy render (%.1fs)...", total)
    run(["ffmpeg", "-y", "-hide_banner", *inputs,
         "-filter_complex", f"{vchain};{achain}",
         "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
         "-c:v", "libx264", "-preset", v["preset"], "-crf", str(v["crf"]),
         "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(v["fps"]),
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", str(out_mp4)])
    log.info("Video tayyor: %s (%.1f MB)", out_mp4.name, out_mp4.stat().st_size / 1e6)
    return out_mp4
