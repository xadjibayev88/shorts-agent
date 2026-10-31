import json
import logging
import os
import subprocess
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("shorts")


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )


def load_config(path: str | None = None) -> dict:
    p = Path(path) if path else ROOT / "config.yaml"
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(name: str, required: bool = True) -> str | None:
    val = os.environ.get(name, "").strip()
    if required and not val:
        raise RuntimeError(f"Muhit o'zgaruvchisi topilmadi: {name} (GitHub Secrets'ga qo'shing)")
    return val or None


def retry(times: int = 3, delay: float = 4.0, backoff: float = 2.0):
    """Xatoda qayta urinish dekoratori."""
    def deco(fn):
        def wrapper(*a, **kw):
            d = delay
            for i in range(1, times + 1):
                try:
                    return fn(*a, **kw)
                except Exception as e:  # noqa: BLE001
                    if i == times:
                        raise
                    log.warning("%s xato (%d/%d): %s — %.0fs kutamiz", fn.__name__, i, times, e, d)
                    time.sleep(d)
                    d *= backoff
        return wrapper
    return deco


def run(cmd: list[str], quiet: bool = True):
    """ffmpeg/ffprobe chaqirish; xatoda stderr oxirini ko'rsatadi."""
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        tail = "\n".join(res.stderr.strip().splitlines()[-25:])
        raise RuntimeError(f"Buyruq xato: {' '.join(cmd[:6])}...\n{tail}")
    if not quiet:
        print(res.stdout)
    return res


def ffprobe_duration(path: str | Path) -> float:
    res = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    return float(res.stdout.strip())


# ---------- tarix (takrorlanmaslik uchun) ----------
HISTORY = ROOT / os.environ.get("HISTORY_FILE", "data/history.json")


def load_history() -> dict:
    if HISTORY.exists():
        try:
            return json.loads(HISTORY.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"videos": [], "used_pexels_ids": [], "genre_index": 0}


def save_history(h: dict):
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    h["used_pexels_ids"] = h.get("used_pexels_ids", [])[-1500:]
    HISTORY.write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")
