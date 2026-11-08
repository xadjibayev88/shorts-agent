"""2D multfilm reel: cartoon/boards/<nom>.json (kadrlar) + <nom>.voice.txt (ovoz matni) -> out/cartoon/<nom>.mp4.

Ovoz agent.tts.synthesize orqali (OmniVoice -> ElevenLabs -> Edge), raqamlar so'z bilan o'qiladi.
ElevenLabs v3 uchun [excited]/[softly] teglari matnda qoladi, boshqa ovozlar uchun olib tashlanadi.
"""
import re
import subprocess
import sys
from pathlib import Path

import yaml

from .tts import synthesize
from .utils import ROOT, log

BOARDS = ROOT / "cartoon" / "boards"
OUT = ROOT / "out" / "cartoon"


def make(name: str, config: str = "config_apex.yaml") -> Path:
    cfg = yaml.safe_load((ROOT / config).read_text(encoding="utf-8"))
    text = (BOARDS / f"{name}.voice.txt").read_text(encoding="utf-8").strip()
    plain = re.sub(r"\[[a-z ]+\]\s*", "", text)  # his-tuyg'u teglari faqat ElevenLabs v3 uchun
    OUT.mkdir(parents=True, exist_ok=True)
    voice = OUT / f"{name}.mp3"
    synthesize(plain, cfg, str(voice))
    out = OUT / f"{name}.mp4"
    subprocess.run([sys.executable, str(ROOT / "cartoon" / "reel.py"), str(BOARDS / f"{name}.json"), str(voice), str(out)], check=True)
    log.info("Tayyor: %s", out)
    return out


if __name__ == "__main__":
    for n in sys.argv[1:]:
        make(n)
