"""Stok videolar: Pixabay (asosiy) yoki Pexels (kalit bo'lsa). Ikkalasi ham bepul.
Hech biri ishlamasa — render chiroyli gradient fon yasaydi."""
import random
import re
from pathlib import Path

import requests

from .utils import env, log, retry


# ---------------- Pixabay ----------------
@retry(times=3, delay=3)
def _pixabay(query: str, min_h: int) -> list[tuple[str, str]]:
    r = requests.get(
        "https://pixabay.com/api/videos/",
        params={"key": env("PIXABAY_API_KEY"), "q": query[:100], "per_page": 50,
                "video_type": "film", "safesearch": "true", "order": "popular"},
        timeout=30,
    )
    r.raise_for_status()
    words = {w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 2}
    ranked = []
    for hit in r.json().get("hits", []):
        # Juda qisqa kliplar odatda harakatsiz — tashlab ketamiz
        if hit.get("duration", 0) < 5:
            continue
        vids = hit.get("videos", {})
        for size in ("large", "medium"):
            f = vids.get(size) or {}
            if f.get("url") and f.get("height", 0) >= min(min_h, 1080) * 0.66:
                # Teglari sahna so'zlariga ko'proq mos keladigan klip — birinchi; tenglikda vertikal klip
                tags = hit.get("tags", "").lower()
                score = sum(1 for w in words if w in tags)
                vertical = f["height"] > f.get("width", 0)
                # Odamlar ko'p yoqtirgan va yuklab olgan klip odatda chiroyliroq va jonliroq
                appeal = hit.get("likes", 0) + hit.get("downloads", 0) / 50
                hd = f.get("height", 0) >= 1080
                ranked.append(((score, hd, vertical, appeal), (f"pb{hit['id']}", f["url"])))
                break
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in ranked]


# ---------------- Pexels ----------------
@retry(times=3, delay=3)
def _pexels(query: str, min_h: int) -> list[tuple[str, str]]:
    r = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": env("PEXELS_API_KEY")},
        params={"query": query, "orientation": "portrait", "per_page": 15, "size": "medium"},
        timeout=30,
    )
    r.raise_for_status()
    out = []
    for v in r.json().get("videos", []):
        files = [f for f in v.get("video_files", [])
                 if f.get("height") and f.get("width") and f["height"] >= f["width"]
                 and f["height"] >= min_h and f.get("file_type") == "video/mp4"]
        if files:
            best = min(files, key=lambda f: abs(f["height"] - 1920))
            out.append((f"px{v['id']}", best["link"]))
    return out


def _providers():
    p = []
    if env("PEXELS_API_KEY", required=False):
        p.append(("Pexels", _pexels))
    if env("PIXABAY_API_KEY", required=False):
        p.append(("Pixabay", _pixabay))
    return p


@retry(times=3, delay=3)
def _download(url: str, dest: Path):
    with requests.get(url, stream=True, timeout=120, headers={"User-Agent": "Mozilla/5.0"}) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def fetch_clips(scenes: list[dict], cfg: dict, history: dict, workdir: Path) -> list[Path | None]:
    """Har sahna uchun bitta klip. Topilmasa None (render gradient fon yasaydi)."""
    providers = _providers()
    if not providers:
        log.warning("PIXABAY_API_KEY ham, PEXELS_API_KEY ham yo'q — gradient fon ishlatiladi")
        return [None] * len(scenes)

    used = {str(x) for x in history.get("used_pexels_ids", [])}
    taken: set[str] = set()
    min_h = cfg["pexels"]["min_height"]
    out: list[Path | None] = []
    for i, sc in enumerate(scenes):
        kw = sc["keywords"]
        queries = [kw, " ".join(kw.split()[:2]), kw.split()[0] if kw.split() else "nature"]
        style = (cfg["pexels"].get("style") or "").strip()
        if style:  # avval kanal uslubidagi kadr (masalan "cinematic"), topilmasa oddiy qidiruv
            queries = [f"{kw} {style}"] + queries
        chosen = None
        for q in queries:
            for name, fn in providers:
                try:
                    items = fn(q, min_h)
                except Exception as e:  # noqa: BLE001
                    log.warning("%s qidiruv xato '%s': %s", name, q, e)
                    continue
                fresh = [x for x in items if x[0] not in used and x[0] not in taken]
                pool = fresh or [x for x in items if x[0] not in taken]
                if pool:
                    chosen = random.choice(pool[:3])
                    log.info("Sahna %d: %s %s ('%s')", i + 1, name, chosen[0], q)
                    break
            if chosen:
                break
        if not chosen:
            log.warning("Sahna %d uchun klip topilmadi — fon ishlatiladi", i + 1)
            out.append(None)
            continue
        dest = workdir / f"clip_{i:02d}.mp4"
        try:
            _download(chosen[1], dest)
            taken.add(chosen[0])
            out.append(dest)
        except Exception as e:  # noqa: BLE001
            log.warning("Yuklab bo'lmadi: %s", e)
            out.append(None)
    history.setdefault("used_pexels_ids", []).extend(sorted(taken))
    return out
