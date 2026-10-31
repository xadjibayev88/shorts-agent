"""Instagram Reels joylash (Instagram API with Instagram Login).

Instagram faylni o'zi yuklab oladi, shuning uchun video vaqtincha ochiq havolaga qo'yiladi:
ochiq GitHub repo (VIDEO_REPO, masalan xadjibayev88/status-videos) + jsDelivr, joylangach o'chiriladi.
Kerakli Secrets: IG_ACCESS_TOKEN, VIDEO_REPO, VIDEO_REPO_TOKEN.
"""
import base64
import time
from datetime import datetime
from pathlib import Path

import requests

from .utils import env, log

GRAPH = "https://graph.instagram.com/v23.0"


def _temp_upload(video: Path) -> tuple[str, callable]:
    repo, tok = env("VIDEO_REPO"), env("VIDEO_REPO_TOKEN")
    path = f"v/{datetime.now():%Y%m%d_%H%M%S}_ig.mp4"
    api = f"https://api.github.com/repos/{repo}/contents/{path}"
    hdr = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}
    raw = video.read_bytes()
    r = requests.put(api, headers=hdr, timeout=600,
                     json={"message": "vaqtincha video", "content": base64.b64encode(raw).decode()})
    if not r.ok:
        raise RuntimeError(f"GitHub xatosi {r.status_code}: {r.text[:300]}")
    j = r.json()
    sha, fsha = j["commit"]["sha"], j["content"]["sha"]
    url = (f"https://cdn.jsdelivr.net/gh/{repo}@{sha}/{path}" if len(raw) <= 19 * 1024 * 1024
           else f"https://raw.githubusercontent.com/{repo}/{sha}/{path}")
    for _ in range(30):
        try:
            if requests.get(url, headers={"Range": "bytes=0-1"}, timeout=30).status_code in (200, 206):
                break
        except requests.RequestException:
            pass
        time.sleep(4)
    else:
        raise RuntimeError(f"Havola ochilmadi: {url}")

    def cleanup():
        try:
            requests.delete(api, headers=hdr, timeout=60, json={"message": "video o'chirildi", "sha": fsha})
        except requests.RequestException as e:
            log.warning("Vaqtincha videoni o'chirib bo'lmadi: %s", e)
    return url, cleanup


def caption(story: dict, cfg: dict) -> str:
    ig = cfg.get("instagram", {})
    parts = [story["title"], story.get("description", "")]
    if ig.get("call_to_action"):
        parts.append(ig["call_to_action"])
    tags = " ".join(ig.get("hashtags") or story.get("hashtags", []))
    return "\n\n".join(p for p in parts + [tags] if p)[:2200]


def publish_reel(video: Path, story: dict, cfg: dict) -> str:
    token = env("IG_ACCESS_TOKEN")
    url, cleanup = _temp_upload(video)
    try:
        r = requests.post(f"{GRAPH}/me/media", timeout=60, data={
            "access_token": token, "media_type": "REELS", "video_url": url,
            "caption": caption(story, cfg), "share_to_feed": "true"})
        if not r.ok:
            raise RuntimeError(f"Instagram xatosi {r.status_code}: {r.text[:400]}")
        cid = r.json()["id"]
        for _ in range(72):
            s = requests.get(f"{GRAPH}/{cid}", timeout=30,
                             params={"access_token": token, "fields": "status_code,status"}).json()
            if s.get("status_code") == "FINISHED":
                break
            if s.get("status_code") in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"Instagram videoni qabul qilmadi: {s}")
            time.sleep(5)
        else:
            raise TimeoutError("Instagram videoni vaqtida qayta ishlamadi")
        r = requests.post(f"{GRAPH}/me/media_publish", timeout=60,
                          data={"access_token": token, "creation_id": cid})
        if not r.ok:
            raise RuntimeError(f"Instagram joylash xatosi {r.status_code}: {r.text[:400]}")
        media_id = r.json().get("id", "")
        log.info("✅ Instagram Reels joylandi: %s", media_id)
        return media_id
    finally:
        cleanup()
