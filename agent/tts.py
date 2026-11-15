"""O'zbekcha ovoz + so'z vaqtlari (subtitr uchun).

ElevenLabs (tabiiy ovoz, ELEVENLABS_API_KEY va tts.elevenlabs_voice bo'lsa) -> aks holda Edge TTS (bepul).
ElevenLabs ishlamasa (kalit yo'q, limit tugagan, xato) avtomatik Edge'ga qaytadi: video baribir chiqadi.
"""
import asyncio
import base64
import os
import re
import subprocess
from pathlib import Path

import edge_tts
import requests

from .numbers_uz import spoken_numbers
from .utils import ROOT, env, ffprobe_duration, log, retry, run

TICKS = 10_000_000  # edge-tts vaqt birligi: 100 ns


async def _synth(text: str, voice: str, rate: str, pitch: str, out_mp3: str):
    try:
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    except TypeError:  # eski versiyalarda boundary parametri yo'q
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    words, sentences = [], []
    with open(out_mp3, "wb") as f:
        async for chunk in comm.stream():
            t = chunk["type"]
            if t == "audio":
                f.write(chunk["data"])
            elif t == "WordBoundary":
                words.append((chunk["offset"] / TICKS, (chunk["offset"] + chunk["duration"]) / TICKS, chunk["text"]))
            elif t == "SentenceBoundary":
                sentences.append((chunk["offset"] / TICKS, (chunk["offset"] + chunk["duration"]) / TICKS, chunk["text"]))
    return words, sentences


def _split_words(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def _spoken_len(tok: str) -> int:
    """So'zning ovozdagi uzunligi: "1968" aslida "bir ming to'qqiz yuz oltmish sakkiz" deb o'qiladi."""
    return len(spoken_numbers(tok)) if any(c.isdigit() for c in tok) else len(tok)


def _distribute(spans: list[tuple[float, float, str]]) -> list[dict]:
    """Gap vaqtini so'zlarga harf uzunligiga qarab taqsimlash (fallback)."""
    out = []
    for start, end, txt in spans:
        toks = _split_words(txt)
        total = sum(_spoken_len(t) + 1 for t in toks) or 1
        cur = start
        for tok in toks:
            d = (end - start) * (_spoken_len(tok) + 1) / total
            out.append({"start": cur, "end": cur + d, "word": tok})
            cur += d
    return out


def _align_to_text(boundaries: list[dict], text: str) -> list[dict]:
    """TTS chegaralarini asl matndagi so'zlarga (tinish belgilari bilan) moslash."""
    toks = _split_words(text)
    if len(boundaries) == len(toks):
        for b, t in zip(boundaries, toks):
            b["word"] = t
        return boundaries
    # Soni mos kelmasa: umumiy vaqt oralig'ida proporsional taqsimlash
    start, end = boundaries[0]["start"], boundaries[-1]["end"]
    return _distribute([(start, end, text)])


def _voice_settings(model: str) -> dict:
    # eleven_v3 stability uchun faqat 0.0 / 0.5 / 1.0 qabul qiladi; 0.5 = tabiiy
    if model.startswith("eleven_v3"):
        return {"stability": 0.5, "similarity_boost": 0.8, "use_speaker_boost": True}
    return {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25, "use_speaker_boost": True}


def _elevenlabs(text: str, voice: str, model: str, out_mp3: str) -> list[dict]:
    """ElevenLabs with-timestamps: audio + har harf vaqti -> so'z vaqtlari."""
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
        headers={"xi-api-key": env("ELEVENLABS_API_KEY"), "Content-Type": "application/json"},
        params={"output_format": "mp3_44100_128"},
        json={"text": text, "model_id": model, "voice_settings": _voice_settings(model)},
        timeout=120,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    with open(out_mp3, "wb") as f:
        f.write(base64.b64decode(data["audio_base64"]))
    al = data.get("alignment") or data.get("normalized_alignment") or {}
    chars, starts, ends = al.get("characters", []), al.get("character_start_times_seconds", []), al.get("character_end_times_seconds", [])
    words, cur, ws, we = [], "", None, None
    for ch, a, b in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append({"start": ws, "end": we, "word": cur})
            cur, ws = "", None
            continue
        if ws is None:
            ws = a
        cur, we = cur + ch, b
    if cur:
        words.append({"start": ws, "end": we, "word": cur})
    return words


def _omnivoice(text: str, o: dict, out_mp3: str) -> None:
    """OmniVoice (omnivoice.cpp, CPU): bepul o'zbekcha ovoz. Ovoz bir xil qolishi uchun doim bitta namunadan klonlanadi."""
    wav = Path(out_mp3).with_suffix(".omni.wav")
    cmd = [os.environ["OMNIVOICE_BIN"], "--model", os.environ["OMNIVOICE_MODEL"], "--codec", os.environ["OMNIVOICE_CODEC"],
           "--lang", o.get("lang", "Uzbek"), "--steps", str(o.get("steps", 16)), "--seed", str(o.get("seed", 7)), "-o", str(wav)]
    if o.get("ref"):
        cmd += ["--ref-wav", str(ROOT / o["ref"]), "--ref-text", str(ROOT / o["ref_text"])]
    res = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=o.get("timeout", 900))
    if res.returncode != 0 or not wav.exists():
        tail = (res.stdout + "\n" + res.stderr).strip().splitlines()[-12:]
        raise RuntimeError(f"OmniVoice xato (kod {res.returncode}): " + " | ".join(tail))
    # boshidagi/oxiridagi jimlikni kesib, mp3 ga aylantiramiz
    run(["ffmpeg", "-y", "-i", str(wav), "-af",
         "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse",
         "-b:a", "192k", out_mp3])
    wav.unlink(missing_ok=True)


def _weighted_words(text: str, duration: float) -> list[dict]:
    """Vaqt belgilari yo'q ovoz uchun: so'z uzunligi + tinish belgidagi pauza bo'yicha taqsimlash."""
    toks = _split_words(text)
    w = [_spoken_len(t) + 1 + (3 if t[-1] in ".!?" else 1.5 if t[-1] in ",;:" else 0) for t in toks]
    total, cur, out = sum(w) or 1, 0.05, []
    span = max(duration - 0.1, 1.0)
    for t, k in zip(toks, w):
        d = span * k / total
        out.append({"start": cur, "end": cur + d * .85, "word": t}); cur += d
    return out


def uz_okina(text: str) -> str:
    """Sardor (Edge) o'/g' ni faqat o'zbekcha okina (U+02BB) bilan to'g'ri o'qiydi; oddiy apostrof bilan "g" va "a" deb o'qiydi."""
    return re.sub(r"([oOgG])['\u2019\u2018\u02bc`]", "\\1\u02bb", text)


def _edge(text: str, spoken: str, t: dict, out_mp3: str) -> tuple[list[dict], float]:
    log.info("Ovoz yozilmoqda (%s)...", t["voice"])
    words, sentences = asyncio.run(_synth(uz_okina(spoken), t["voice"], t["rate"], t["pitch"], out_mp3))
    duration = ffprobe_duration(out_mp3)
    if duration < 0.5:
        raise RuntimeError("Edge TTS ovoz bermadi")
    if words:
        timed = [{"start": s, "end": e, "word": w} for s, e, w in words]
        timed = _align_to_text(timed, text)
    elif sentences:
        timed = _distribute(sentences)
    else:
        timed = _distribute([(0.15, max(duration - 0.2, 1.0), text)])
    log.info("Ovoz: %.1fs, %d so'z vaqti (Edge)", duration, len(timed))
    return timed, duration


@retry(times=3, delay=4)
def synthesize(text: str, cfg: dict, out_mp3: str) -> tuple[list[dict], float]:
    t = cfg["tts"]
    o = t.get("omnivoice") or {}
    # Ovoz modellari raqamlarni tashlab ketadi: ovozga so'z bilan beramiz, subtitr (text) raqamligicha qoladi
    spoken = spoken_numbers(text)
    if spoken != text:
        log.info("Ovoz matni (raqamlar so'z bilan): %s", spoken)
    if t.get("engine") == "edge":  # multfilm-studio bilan bir xil ovoz: Edge Sardor + aniq so'z vaqtlari
        try:
            return _edge(text, spoken, t, out_mp3)
        except Exception as e:  # noqa: BLE001 — ishlamasa eski zanjir (OmniVoice -> ElevenLabs -> Edge)
            log.warning("Edge TTS ishlamadi: %s", e)
    if o.get("enabled") and os.environ.get("OMNIVOICE_BIN") and Path(os.environ["OMNIVOICE_BIN"]).exists():
        try:
            log.info("Ovoz yozilmoqda (OmniVoice, %s qadam)...", o.get("steps", 16))
            _omnivoice(spoken, o, out_mp3)
            duration = ffprobe_duration(out_mp3)
            timed = _weighted_words(text, duration)
            log.info("Ovoz: %.1fs (OmniVoice)", duration)
            return timed, duration
        except Exception as e:  # noqa: BLE001 — ishlamasa ElevenLabs/Edge
            log.warning("OmniVoice ishlamadi: %s", e)
    if env("ELEVENLABS_API_KEY", required=False):
        # Navbat bilan: asosiy ovoz (o'zbekcha, v3) -> zaxira ovoz -> Edge TTS
        options = [(t["elevenlabs_voice"], t.get("elevenlabs_model", "eleven_multilingual_v2"))] if t.get("elevenlabs_voice") else []
        if t.get("elevenlabs_backup_voice"):
            options.append((t["elevenlabs_backup_voice"], t.get("elevenlabs_backup_model", "eleven_multilingual_v2")))
        for voice, model in options:
            try:
                log.info("Ovoz yozilmoqda (ElevenLabs %s, %s)...", voice, model)
                timed = _elevenlabs(spoken, voice, model, out_mp3)
                duration = ffprobe_duration(out_mp3)
                timed = _align_to_text(timed, text) if timed else _distribute([(0.15, max(duration - 0.2, 1.0), text)])
                log.info("Ovoz: %.1fs, %d so'z vaqti (ElevenLabs %s)", duration, len(timed), model)
                return timed, duration
            except Exception as e:  # noqa: BLE001 — limit tugasa ham video chiqsin
                log.warning("ElevenLabs (%s, %s) ishlamadi: %s", voice, model, e)
        if options:
            log.warning("ElevenLabs ishlamadi, Edge TTS ishlatiladi")
    return _edge(text, spoken, t, out_mp3)
