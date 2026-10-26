"""Edge TTS (bepul) — o'zbekcha ovoz + so'z vaqtlari (subtitr uchun)."""
import asyncio
import re

import edge_tts

from .utils import ffprobe_duration, log, retry

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


@retry(times=3, delay=4)
def synthesize(text: str, cfg: dict, out_mp3: str) -> tuple[list[dict], float]:
    t = cfg["tts"]
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
