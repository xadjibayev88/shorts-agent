"""Pexels'dan vertikal stok videolar yuklab olish (bepul API)."""
import random
from pathlib import Path

import requests

from .utils import env, log, retry

SEARCH = "https://api.pexels.com/videos/search"


@retry(times=3, delay=3)
def _search(query: str, per_page: int, orientation: str = "portrait") -> list[dict]:
    r = requests.get(
        SEARCH,
        headers={"Authorization": env("PEXELS_API_KEY")},
        params={"query": query, "orientation": orientation, "per_page": per_page, "size": "medium"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("videos", [])


def _best_file(video: dict, min_h: int) -> dict | None:
    files = [f for f in video.get("video_files", [])
             if f.get("height") and f.get("width") and f["height"] >= f["width"]
             and f["height"] >= min_h and f.get("file_type") == "video/mp4"]
    if not files:
        return None
    # 1920 ga eng yaqinini olamiz (4K emas — tezroq)
    return min(files, key=lambda f: abs(f["height"] - 1920))


@retry(times=3, delay=3)
def _download(url: str, dest: Path):
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def fetch_clips(scenes: list[dict], cfg: dict, history: dict, workdir: Path) -> list[Path | None]:
    """Har sahna uchun bitta klip. Topilmasa None (render fon yasaydi)."""
    used = set(history.get("used_pexels_ids", []))
    taken_now: set[int] = set()
    min_h = cfg["pexels"]["min_height"]
    out: list[Path | None] = []
    for i, sc in enumerate(scenes):
        queries = [sc["keywords"], " ".join(sc["keywords"].split()[:2]), "cinematic mood"]
        chosen = None
        for q in queries:
            try:
                vids = _search(q, cfg["pexels"]["per_page"])
            except Exception as e:  # noqa: BLE001
                log.warning("Pexels qidiruv xato '%s': %s", q, e)
                continue
            fresh = [v for v in vids if v["id"] not in used and v["id"] not in taken_now]
            pool = fresh or [v for v in vids if v["id"] not in taken_now]
            random.shuffle(pool)
            for v in pool[:6]:
                f = _best_file(v, min_h)
                if f:
                    chosen = (v["id"], f["link"])
                    break
            if chosen:
                break
        if not chosen:
            log.warning("Sahna %d uchun klip topilmadi — fon ishlatiladi", i + 1)
            out.append(None)
            continue
        vid, link = chosen
        dest = workdir / f"clip_{i:02d}.mp4"
        try:
            _download(link, dest)
            taken_now.add(vid)
            out.append(dest)
            log.info("Sahna %d: Pexels #%s ('%s')", i + 1, vid, sc["keywords"])
        except Exception as e:  # noqa: BLE001
            log.warning("Yuklab bo'lmadi: %s", e)
            out.append(None)
    history.setdefault("used_pexels_ids", []).extend(sorted(taken_now))
    return out
