"""Builds a demo spec + synthesised public-domain melody (Twinkle Twinkle) for agent.lyric_toon."""
import json
import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100
BEAT = 0.6
HZ = {"C": 261.63, "D": 293.66, "E": 329.63, "F": 349.23, "G": 392.0, "A": 440.0}
A = "C C G G A A G:2 F F E E D D C:2".split()
B = "G G F F E E D:2 G G F F E E D:2".split()
PHRASES = [
    ("Twinkle, twinkle, little star", A[:7]),
    ("How I wonder what you are", A[7:]),
    ("Up above the world so high", B[:7]),
    ("Like a diamond in the sky", B[7:]),
    ("Twinkle, twinkle, little star", A[:7]),
    ("How I wonder what you are", A[7:]),
]


def tone(f, dur):
    t = np.arange(int(SR * dur)) / SR
    env = np.minimum(1, t / 0.01) * np.exp(-t * 2.2)
    return env * (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t))


def main(out_dir: str) -> None:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    lead = 3.0
    audio = [np.zeros(int(SR * lead))]
    lines, t = [], lead
    for text, notes in PHRASES:
        start = t
        for n in notes:
            name, _, b = n.partition(":")
            dur = BEAT * (int(b) if b else 1)
            audio.append(tone(HZ[name], dur))
            t += dur
        lines.append({"t0": round(start, 2), "t1": round(t, 2), "text": text})
    y = np.concatenate(audio)
    y = (y / np.abs(y).max() * 0.6 * 32767).astype(np.int16)
    with wave.open(str(out / "melody.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(y.tobytes())
    spec = {"audio": str(out / "melody.wav"), "handle": "@apex_wealths",
            "intro": [{"t0": 0.2, "t1": 1.5, "text": "Bugun nima qilding, o'g'lim?"}, {"t0": 1.6, "t1": 2.8, "text": "Hmm..."}],
            "lines": lines}
    (out / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
