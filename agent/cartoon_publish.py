"""cartoon/publish_queue.json dagi navbatdagi 2D multfilm reelni apex_wealths YouTube + Instagram'ga joylaydi.

Har ishga tushishda bitta video (soatlik cron). Video cartoon-out shoxidan, sarlavha/tavsif esa
fakt-tekshiruvdan o'tgan hikoyadan (queue_apex/ yoki queue_apex/done/) olinadi. Joylangan hikoya
tarixga yoziladi, shuning uchun oddiy apex pipeline o'sha mavzuni qayta chiqarmaydi.
"""
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .utils import ROOT, load_config, load_history, log, save_history, setup_logging

QUEUE = ROOT / "cartoon" / "publish_queue.json"
STORIES = ROOT / "queue_apex"


def _story(name: str) -> tuple[dict, Path]:
    for p in (STORIES / name, STORIES / "done" / name):  # rejected/ dagilar joylanmaydi
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")), p
    raise FileNotFoundError(name)


def _video(name: str) -> Path:
    out = ROOT / "out" / "cartoon" / f"{name}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "fetch", "-q", "origin", "cartoon-out"], cwd=ROOT, check=True)
    out.write_bytes(subprocess.run(["git", "show", f"origin/cartoon-out:{name}.mp4"], cwd=ROOT, check=True, capture_output=True).stdout)
    return out


def publish_next(cfg: dict) -> dict | None:
    history = load_history()
    # Faqat multfilm versiyasi joylanganlarni o'tkazamiz (oddiy video joylangan bo'lsa ham multfilm chiqadi)
    used = {v["title"].lower() for v in history.get("videos", []) if v.get("format") == "cartoon"}
    for item in json.loads(QUEUE.read_text(encoding="utf-8")):
        story, path = _story(item["story"])
        if story["title"].lower() in used:
            continue
        video = _video(item["video"])
        cfg["youtube"]["description_footer"] = (cfg["youtube"].get("description_footer", "") +
                                                "\nAnimatsiya kod bilan chizilgan, ovoz sun'iy intellekt.").strip()
        video_id = ig_id = None
        if os.environ.get("YT_REFRESH_TOKEN"):
            from .uploader import upload
            try:
                video_id = upload(video, story, cfg)
            except Exception as e:  # noqa: BLE001 — Instagram baribir urinadi
                log.warning("YouTube'ga joylanmadi: %s", e)
        if os.environ.get("IG_ACCESS_TOKEN"):
            from .instagram import publish_reel
            try:
                ig_id = publish_reel(video, story, cfg)
            except Exception as e:  # noqa: BLE001
                log.warning("Instagram'ga joylanmadi: %s", e)
        if not (video_id or ig_id):
            raise RuntimeError(f"{item['video']} hech qayerga joylanmadi")
        history.setdefault("videos", []).append({
            "date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "title": story["title"],
            "format": "cartoon", "video_id": video_id, "instagram_id": ig_id,
            "words": len(" ".join(s["text"] for s in story.get("scenes", [])).split())})
        save_history(history)
        if path.parent == STORIES:  # navbatdagi hikoya endi done/ ga
            (STORIES / "done").mkdir(exist_ok=True)
            path.rename(STORIES / "done" / path.name)
        log.info("Joylandi: %s (YouTube %s, Instagram %s)", item["video"], video_id, ig_id)
        return {"video": item["video"], "youtube": video_id, "instagram": ig_id}
    log.info("Multfilm navbati bo'sh — hammasi joylangan")
    return None


if __name__ == "__main__":
    setup_logging()
    publish_next(load_config("config_apex.yaml"))
