"""Gemini orqali o'zbekcha qisqa hikoya + sahnalar + YouTube metadata yaratish."""
import json
import re

import requests

from .utils import env, log, retry

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """Sen YouTube Shorts uchun virusli qisqa hikoyalar yozadigan professional ssenariynavissan.
Kanal: o'zbek tilidagi "{niche}". Bugungi janr: {genre}.

VAZIFA: butunlay ORIGINAL, to'qima qahramonli qisqa hikoya yoz (real shaxslar, siyosat, din mavzularida bahs yo'q).
Talablar:
- Til: sof, jonli adabiy o'zbek tili (lotin yozuvi). O' va G' uchun oddiy apostrof ishlat: o', g'.
- Hikoya {min_words}-{max_words} so'zdan iborat bo'lsin (ovozda ~45-55 soniya).
- 1-gap — kuchli HOOK: tomoshabinni birinchi 2 soniyada ushlab qolsin (savol, sir yoki shok fakt).
- O'rtada taranglik oshib borsin, oxirida kutilmagan burilish yoki chuqur xulosa bo'lsin.
- Oxirgi gap qisqa va esda qoladigan bo'lsin. "Obuna bo'ling" deb yozma.
- Gaplar qisqa, ovozda o'qishga qulay. Raqamlarni so'z bilan yoz. Emoji ishlatma.
- Hikoyani {scenes_min}-{scenes_max} ta sahnaga bo'l. Har sahna uchun Pexels stok videodan
  qidirish uchun 2-4 so'zli INGLIZCHA kalit so'z ber (aniq, vizual: "old man walking village",
  "rainy city night", "hands counting money"). Yuz/odam aniq bo'lmagan, kayfiyatga mos kadrlar yaxshi.

Shu sarlavhalar ALLAQACHON ishlatilgan, takrorlama va ularga o'xshatma:
{used}

FAQAT shu JSON formatda javob ber:
{{
  "title": "Qiziqarli sarlavha, 40-70 belgi, clickbait lekin halol",
  "hook": "Ekran tepasidagi 2-5 so'zli qisqa ilmoq matni",
  "scenes": [
    {{"text": "sahnadagi ovozli matn (1-3 gap)", "keywords": "english search words"}}
  ],
  "description": "2-3 gaplik tavsif, hikoyani ochib bermasdan qiziqtiradi",
  "tags": ["8-12 ta o'zbekcha va inglizcha teg"],
  "hashtags": ["#3-5", "#ta", "#heshteg"]
}}
"""


def _word_count(s: str) -> int:
    return len(re.findall(r"\w[\w']*", s))


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("Javobda JSON topilmadi")
    return json.loads(m.group(0))


def _call_gemini(model: str, prompt: str, temperature: float) -> str:
    key = env("GEMINI_API_KEY")
    r = requests.post(
        API.format(model=model),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
            },
        },
        timeout=120,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Gemini {model} HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def validate(story: dict, cfg: dict) -> dict:
    sc = cfg["story"]
    scenes = [s for s in story.get("scenes", []) if s.get("text", "").strip()]
    if len(scenes) < 3:
        raise ValueError(f"Sahnalar juda kam: {len(scenes)}")
    for s in scenes:
        s["text"] = re.sub(r"\s+", " ", s["text"]).strip()
        s["keywords"] = (s.get("keywords") or "nature landscape").strip()
    words = sum(_word_count(s["text"]) for s in scenes)
    if not (sc["min_words"] * 0.85 <= words <= sc["max_words"] * 1.15):
        raise ValueError(f"So'z soni mos emas: {words}")
    story["scenes"] = scenes
    story["title"] = story.get("title", "Qiziqarli hikoya").strip()[:90]
    story["hook"] = (story.get("hook") or "").strip()[:40]
    story["tags"] = [t.strip("# ").strip() for t in story.get("tags", []) if t.strip()][:15]
    story["hashtags"] = [h if h.startswith("#") else f"#{h}" for h in story.get("hashtags", [])][:5]
    story["description"] = story.get("description", "").strip()
    story["word_count"] = words
    return story


@retry(times=3, delay=5)
def generate_story(cfg: dict, history: dict) -> dict:
    genres = cfg["channel"]["genres"]
    gi = history.get("genre_index", 0) % len(genres)
    genre = genres[gi]
    used = [v["title"] for v in history.get("videos", [])][-cfg["story"]["history_avoid_last"]:]
    prompt = PROMPT.format(
        niche=cfg["channel"]["niche"], genre=genre,
        min_words=cfg["story"]["min_words"], max_words=cfg["story"]["max_words"],
        scenes_min=cfg["story"]["scenes_min"], scenes_max=cfg["story"]["scenes_max"],
        used="\n".join(f"- {t}" for t in used) or "- (hali yo'q)",
    )
    last_err = None
    for model in cfg["gemini"]["models"]:
        try:
            log.info("Gemini (%s) hikoya yozmoqda — janr: %s", model, genre)
            raw = _call_gemini(model, prompt, cfg["gemini"]["temperature"])
            story = validate(_extract_json(raw), cfg)
            used_lower = {t.lower() for t in used}
            if story["title"].lower() in used_lower:
                raise ValueError("Sarlavha takrorlandi")
            story["genre"] = genre
            story["model"] = model
            history["genre_index"] = gi + 1
            log.info("Hikoya tayyor: «%s» (%d so'z, %d sahna)",
                     story["title"], story["word_count"], len(story["scenes"]))
            return story
        except Exception as e:  # noqa: BLE001
            last_err = e
            log.warning("Model %s ishlamadi: %s", model, e)
    raise RuntimeError(f"Hech bir Gemini modeli hikoya bermadi: {last_err}")
