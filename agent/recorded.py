"""Egasining o'z ovozi (TTS emas) bilan video.

Ish tartibi:
  1. `python -m agent.main --config config_apex.yaml --prepare 3` — ssenariylar yoziladi (fakt-tekshiruv bilan)
     va ovoz_apex/kutmoqda/ ga `NN_nom.json` + `NN_nom.txt` (o'qiladigan matn) bo'lib tushadi.
  2. Egasi .txt dagi matnni telefonda o'qib yozadi va faylni o'sha papkaga `NN.m4a` (yoki `NN_nom.m4a`,
     mp3/ogg/opus/wav/aac/webm ham bo'ladi) nomi bilan yuklaydi.
  3. Kunlik ishga tushishda ovozi tayyor birinchi ssenariy olinadi: ovoz tozalanadi (shovqin, balandlik,
     uzun pauzalar), so'z vaqtlari Whisper bilan ovozning o'zidan olinadi, video yig'iladi va joylanadi.
     Ovoz yo'q bo'lsa hech narsa joylanmaydi (kompyuter ovoziga qaytilmaydi).
"""
import difflib
import json
import os
import re
from pathlib import Path

from .tts import _split_words, _weighted_words
from .utils import ROOT, ffprobe_duration, log, run

AUDIO_EXT = {".m4a", ".mp3", ".ogg", ".oga", ".opus", ".wav", ".aac", ".webm", ".mp4", ".amr", ".flac", ".3gp"}


class NoRecording(Exception):
    """Ovozi yozilgan ssenariy hali yo'q."""


def _dirs(cfg: dict) -> tuple[Path, Path]:
    base = ROOT / cfg["tts"].get("recorded_dir", "ovoz_apex")
    return base / "kutmoqda", base / "done"


def narration_of(story: dict) -> str:
    return " ".join(s["text"] for s in story["scenes"])


def _audio_for(js: Path) -> Path | None:
    """`07_nom.json` uchun `07_nom.*` yoki `07.*` ovoz fayli."""
    num = js.stem.split("_", 1)[0]
    for p in sorted(js.parent.iterdir()):
        if p.suffix.lower() in AUDIO_EXT and (p.stem == js.stem or p.stem.split("_", 1)[0] == num):
            return p
    return None


def pending(cfg: dict) -> list[Path]:
    wait, _ = _dirs(cfg)
    return sorted(wait.glob("*.json")) if wait.exists() else []


def next_ready(cfg: dict) -> tuple[dict, Path, Path]:
    for js in pending(cfg):
        audio = _audio_for(js)
        if audio:
            story = json.loads(js.read_text(encoding="utf-8"))
            log.info("Ovozi tayyor ssenariy: %s (%s)", js.name, audio.name)
            return story, js, audio
    raise NoRecording(f"{len(pending(cfg))} ta ssenariy ovoz kutmoqda")


def finish(cfg: dict, js: Path, audio: Path) -> None:
    _, done = _dirs(cfg)
    done.mkdir(parents=True, exist_ok=True)
    for p in (js, js.with_suffix(".txt"), audio):
        if p.exists():
            p.rename(done / p.name)


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", title.lower().replace("'", "").replace("ʻ", "")).strip("_")
    return s[:40] or "ssenariy"


def prepare(cfg: dict, history: dict, upto: int) -> list[Path]:
    """Ovoz kutayotgan ssenariylar soni `upto` ga yetguncha yangilarini yozadi."""
    from .story import generate_story

    wait, done = _dirs(cfg)
    wait.mkdir(parents=True, exist_ok=True)
    taken = {json.loads(p.read_text(encoding="utf-8"))["title"].lower()
             for d in (wait, done) if d.exists() for p in d.glob("*.json")}
    nums = [int(p.stem.split("_", 1)[0]) for d in (wait, done) if d.exists()
            for p in d.glob("*.json") if p.stem.split("_", 1)[0].isdigit()]
    nxt, made = max(nums, default=0) + 1, []
    # Hali joylanmagan, lekin kutayotgan sarlavhalar ham takrorlanmasin
    hist = {**history, "videos": history.get("videos", []) + [{"title": t} for t in taken]}
    while len(pending(cfg)) < upto:
        story = generate_story(cfg, hist)
        if story["title"].lower() in taken:
            continue
        taken.add(story["title"].lower())
        hist["videos"].append({"title": story["title"]})
        history["genre_index"] = hist.get("genre_index", 0)
        name = f"{nxt:02d}_{_slug(story['title'])}"
        js = wait / f"{name}.json"
        js.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
        text = narration_of(story)
        (wait / f"{name}.txt").write_text(
            f"{story['title']}\n\nShu matnni o'qib yozing va faylni shu papkaga «{nxt:02d}.m4a» nomi bilan yuklang.\n"
            f"Raqamlarni so'z bilan o'qing. Taxminan {len(text.split())} so'z.\n\n"
            + "\n\n".join(s["text"] for s in story["scenes"]) + "\n",
            encoding="utf-8")
        log.info("Ssenariy yozildi: %s «%s»", js.name, story["title"])
        made.append(js)
        nxt += 1
    return made


# ---------------- ovozni tozalash ----------------
def clean_audio(src: Path, out_mp3: Path) -> float:
    """Telefon yozuvi -> tiniq ovoz: past g'uvillash va shovqin olinadi, boshi/oxiridagi va 0.7 s dan uzun
    pauzalar qisqartiriladi, ovoz bir tekis va baland (-16 LUFS) qilinadi."""
    af = ",".join([
        "highpass=f=80", "lowpass=f=13000",
        "afftdn=nf=-25:tn=1",
        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15",
        "silenceremove=stop_periods=-1:stop_duration=0.7:stop_threshold=-45dB:stop_silence=0.35",
        "acompressor=threshold=-20dB:ratio=3:attack=5:release=90:makeup=2",
        "loudnorm=I=-16:TP=-1.5:LRA=9",
    ])
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "1",
         "-af", af, "-ar", "48000", "-b:a", "192k", str(out_mp3)])
    dur = ffprobe_duration(str(out_mp3))
    if dur < 3:
        raise RuntimeError(f"Ovoz fayli juda qisqa yoki bo'sh: {src.name} ({dur:.1f}s)")
    log.info("Ovoz tozalandi: %s -> %.1fs", src.name, dur)
    return dur


# ---------------- so'z vaqtlari ----------------
def _norm(w: str) -> str:
    w = w.lower().replace("ʻ", "'").replace("’", "'").replace("ʼ", "'").replace("`", "'")
    return re.sub(r"[^\w']", "", w)


def _whisper_words(audio: Path, prompt: str) -> list[tuple[str, float, float]]:
    from faster_whisper import WhisperModel  # ixtiyoriy kutubxona: yo'q bo'lsa ImportError

    import subprocess

    import numpy as np

    # Ovozni o'zimiz ffmpeg bilan 16 kHz ga o'giramiz: faster-whisper ichidagi PyAV yangi versiyalarda buziladi
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    pcm = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    model = WhisperModel(os.environ.get("WHISPER_MODEL", "small"), device="cpu", compute_type="int8")
    segs, _ = model.transcribe(pcm, language="uz", word_timestamps=True,
                               initial_prompt=prompt[:400], vad_filter=False)
    return [(_norm(w.word), w.start, w.end) for s in segs for w in (s.words or []) if _norm(w.word)]


def _fill(toks: list[str], times: list, dur: float) -> list[dict]:
    """Moslangan so'zlar orasidagi moslanmaganlarga vaqtni harf uzunligi bo'yicha bo'lib beradi."""
    n, out, i = len(toks), [None] * len(toks), 0
    while i < n:
        if times[i] is not None:
            out[i] = {"start": times[i][0], "end": times[i][1], "word": toks[i]}
            i += 1
            continue
        j = i
        while j < n and times[j] is None:
            j += 1
        a = times[i - 1][1] if i > 0 else 0.05
        b = times[j][0] if j < n else dur - 0.05
        b = max(b, a + 0.1 * (j - i))
        w = [len(t) + 1 for t in toks[i:j]]
        cur = a
        for k in range(i, j):
            d = (b - a) * w[k - i] / sum(w)
            out[k] = {"start": cur, "end": cur + d * 0.9, "word": toks[k]}
            cur += d
        i = j
    return out


def align(text: str, audio: Path, dur: float) -> list[dict]:
    """Ssenariy so'zlariga yozuvdagi haqiqiy vaqtni beradi (subtitr ovoz bilan bir vaqtda chiqadi)."""
    toks = _split_words(text)
    try:
        heard = _whisper_words(audio, text)
    except Exception as e:  # noqa: BLE001 — Whisper bo'lmasa ham video chiqsin
        log.warning("Whisper ishlamadi (%s) — so'z vaqtlari taxminiy", e)
        return _weighted_words(text, dur)
    sm = difflib.SequenceMatcher(None, [_norm(t) for t in toks], [h[0] for h in heard], autojunk=False)
    times = [None] * len(toks)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            _, s, e = heard[blk.b + k]
            times[blk.a + k] = (s, e)
    hit = sum(t is not None for t in times)
    log.info("Whisper: %d so'z eshitildi, ssenariyning %d/%d so'zi moslandi", len(heard), hit, len(toks))
    if hit < max(3, len(toks) * 0.25):
        if heard:  # matn yozuvdan farq qiladi: hech bo'lmasa nutq boshlanish/tugashini olamiz
            return [{**w, "start": heard[0][1] + w["start"] * (heard[-1][2] - heard[0][1]) / dur,
                     "end": heard[0][1] + w["end"] * (heard[-1][2] - heard[0][1]) / dur}
                    for w in _weighted_words(text, dur)]
        return _weighted_words(text, dur)
    return _fill(toks, times, dur)
