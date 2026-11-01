"""O'zbekcha ovoz + so'z vaqtlari (subtitr uchun).

ElevenLabs (tabiiy ovoz, ELEVENLABS_API_KEY va tts.elevenlabs_voice bo'lsa) -> aks holda Edge TTS (bepul).
ElevenLabs ishlamasa (kalit yo'q, limit tugagan, xato) avtomatik Edge'ga qaytadi: video baribir chiqadi.
"""
import asyncio
import base64
import re

import edge_tts
import requests

from .utils import env, ffprobe_duration, log, retry

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


def _distribute(spans: list[tuple[float, float, str]]) -> list[dict]:
    """Gap vaqtini so'zlarga harf uzunligiga qarab taqsimlash (fallback)."""
    out = []
    for start, end, txt in spans:
        toks = _split_words(txt)
        total = sum(len(t) + 1 for t in toks) or 1
        cur = start
        for tok in toks:
            d = (end - start) * (len(tok) + 1) / total
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


@retry(times=3, delay=4)
def synthesize(text: str, cfg: dict, out_mp3: str) -> tuple[list[dict], float]:
    t = cfg["tts"]
    if env("ELEVENLABS_API_KEY", required=False):
        # Navbat bilan: asosiy ovoz (o'zbekcha, v3) -> zaxira ovoz -> Edge TTS
        options = [(t["elevenlabs_voice"], t.get("elevenlabs_model", "eleven_multilingual_v2"))] if t.get("elevenlabs_voice") else []
        if t.get("elevenlabs_backup_voice"):
            options.append((t["elevenlabs_backup_voice"], t.get("elevenlabs_backup_model", "eleven_multilingual_v2")))
        for voice, model in options:
            try:
                log.info("Ovoz yozilmoqda (ElevenLabs %s, %s)...", voice, model)
                timed = _elevenlabs(text, voice, model, out_mp3)
                duration = ffprobe_duration(out_mp3)
                timed = _align_to_text(timed, text) if timed else _distribute([(0.15, max(duration - 0.2, 1.0), text)])
                log.info("Ovoz: %.1fs, %d so'z vaqti (ElevenLabs %s)", duration, len(timed), model)
                return timed, duration
            except Exception as e:  # noqa: BLE001 — limit tugasa ham video chiqsin
                log.warning("ElevenLabs (%s, %s) ishlamadi: %s", voice, model, e)
        if options:
            log.warning("ElevenLabs ishlamadi, Edge TTS ishlatiladi")
    log.info("Ovoz yozilmoqda (%s)...", t["voice"])
    words, sentences = asyncio.run(_synth(text, t["voice"], t["rate"], t["pitch"], out_mp3))
    duration = ffprobe_duration(out_mp3)
    if words:
        timed = [{"start": s, "end": e, "word": w} for s, e, w in words]
        timed = _align_to_text(timed, text)
    elif sentences:
        timed = _distribute(sentences)
    else:
        timed = _distribute([(0.15, max(duration - 0.2, 1.0), text)])
    log.info("Ovoz: %.1fs, %d so'z vaqti", duration, len(timed))
    return timed, duration
