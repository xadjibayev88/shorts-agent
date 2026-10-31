"""
YouTube Shorts Agent — bitta ishga tushirishda 1 ta (yoki --count N) Shorts yaratib joylaydi.

  python -m agent.main                 # yaratish + YouTube'ga joylash
  python -m agent.main --no-upload     # faqat video yasash (sinov)
  python -m agent.main --story samples/sample_story.json --no-upload
"""
import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .utils import ROOT, load_config, load_history, log, save_history, setup_logging


QUEUE = ROOT / "queue"


def _move(path: Path, sub: str) -> None:
    dest = QUEUE / sub
    dest.mkdir(parents=True, exist_ok=True)
    path.rename(dest / path.name)


def next_queued(cfg: dict, history: dict):
    """queue/*.json dagi tayyor ssenariylar navbat bilan (fayl nomi tartibida) ishlatiladi.

    Har biri ham internet orqali fakt-tekshiruvdan o'tadi; o'tmasa queue/rejected/ ga tushadi.
    Qaytaradi: (story, fayl) yoki (None, None).
    """
    from .story import FactError, _fact_check, _llm_chain, validate

    used = {v["title"].lower() for v in history.get("videos", [])}
    for path in sorted(QUEUE.glob("*.json")):
        try:
            story = validate(json.loads(path.read_text(encoding="utf-8")), cfg)
            if story["title"].lower() in used:
                log.info("Navbatdagi «%s» allaqachon joylangan — done/ ga", story["title"])
                _move(path, "done")
                continue
            _fact_check(story, _llm_chain(cfg), "queue", cfg)
        except FactError as e:
            log.warning("Navbatdagi %s fakt-tekshiruvdan o'tmadi: %s", path.name, e)
            _move(path, "rejected")
            continue
        except Exception as e:  # noqa: BLE001
            # Tekshiruvchi ishlamadi va h.k. — fayl navbatda qoladi, keyingi safar yana urinadi
            log.warning("Navbatdagi %s hozircha ishlatilmadi: %s", path.name, e)
            return None, None
        sites = list(dict.fromkeys(s["title"] for s in story.get("fact_sources", []) if s.get("title")))[:3]
        if sites:
            story["description"] += "\nTekshirildi: " + ", ".join(sites)
        story["model"] = "queue"
        log.info("Navbatdan olindi: %s «%s»", path.name, story["title"])
        return story, path
    return None, None


def make_one(cfg: dict, history: dict, args) -> dict:
    from .media import fetch_clips
    from .render import render
    from .story import generate_story, validate
    from .tts import synthesize

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    workdir = ROOT / "output" / stamp
    workdir.mkdir(parents=True, exist_ok=True)

    # 1) Hikoya: qo'lda berilgan fayl > queue/ navbati > model yozadi
    queued = None
    if args.story:
        story = validate(json.loads(Path(args.story).read_text(encoding="utf-8")), cfg)
    else:
        story, queued = next_queued(cfg, history)
        if story is None:
            story = generate_story(cfg, history)
    (workdir / "story.json").write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2) Ovoz
    narration = " ".join(s["text"] for s in story["scenes"])
    voice = workdir / "voice.mp3"
    words, dur = synthesize(narration, cfg, str(voice))

    # 3) Kadrlar
    if args.no_stock:
        clips = [None] * len(story["scenes"])
    else:
        clips = fetch_clips(story["scenes"], cfg, history, workdir)

    # 4) Montaj
    out = workdir / "short.mp4"
    render(story, clips, voice, words, dur, cfg, workdir, out)

    # 5) Joylash
    video_id = None
    if not args.no_upload:
        from .uploader import upload
        video_id = upload(out, story, cfg)

    record = {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "title": story["title"],
        "genre": story.get("genre"),
        "video_id": video_id,
        "words": story["word_count"],
    }
    if video_id:
        history.setdefault("videos", []).append(record)
    if queued and video_id:  # sinov (--no-upload) navbatni sarflamaydi
        _move(queued, "done")

    # Joy tejash: oraliq fayllarni o'chiramiz
    if not args.keep_temp:
        for p in workdir.glob("*"):
            if p.name not in {"short.mp4", "story.json", "subs.ass"}:
                p.unlink(missing_ok=True)
    return {**record, "file": str(out)}


def main():
    setup_logging()
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1, help="nechta video")
    ap.add_argument("--no-upload", action="store_true", help="YouTube'ga joylamaslik")
    ap.add_argument("--no-stock", action="store_true", help="Pexels o'rniga gradient fon")
    ap.add_argument("--story", help="tayyor hikoya JSON fayli (Gemini'siz)")
    ap.add_argument("--keep-temp", action="store_true")
    ap.add_argument("--config")
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg o'rnatilmagan")

    from .notify import telegram

    cfg = load_config(args.config)
    history = load_history()
    ok, fail = 0, 0
    for n in range(args.count):
        try:
            log.info("========== Video %d/%d ==========", n + 1, args.count)
            r = make_one(cfg, history, args)
            ok += 1
            if r["video_id"]:
                telegram(f"✅ Yangi Shorts joylandi:\n{r['title']}\nhttps://youtube.com/shorts/{r['video_id']}")
        except Exception as e:  # noqa: BLE001
            fail += 1
            log.exception("Video yasashda xato: %s", e)
            telegram(f"❌ Shorts agent xatosi: {str(e)[:300]}")
        finally:
            save_history(history)
        if n + 1 < args.count:
            time.sleep(5)
    log.info("Yakun: %d muvaffaqiyatli, %d xato", ok, fail)
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
