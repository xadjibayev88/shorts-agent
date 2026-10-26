"""Gemini orqali o'zbekcha qisqa hikoya + sahnalar + YouTube metadata yaratish."""
import json
import re

import requests

from .utils import env, log, retry

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """Sen "Bilarmidingiz" nomli o'zbek tilidagi YouTube Shorts kanali uchun virusli fakt-videolar yozadigan ssenariynavissan.
Kanal yo'nalishi: "{niche}". Bugungi mavzu: {genre}.

VAZIFA: shu mavzu bo'yicha bitta HAQIQIY, ilmiy tasdiqlangan, hayratlanarli faktni tanla va u haqida qisqa video matni yoz.
Talablar:
- Fakt to'qima bo'lmasin. Shubhali, afsonaviy yoki tekshirib bo'lmaydigan faktlarni tanlama. Raqamlar aniq bo'lsin.
- Til: sof, jonli o'zbek tili (lotin yozuvi). O' va G' uchun oddiy apostrof ishlat: o', g'.
- Matn {min_words}-{max_words} so'zdan iborat bo'lsin (ovozda ~35-50 soniya).
- 1-gap ALBATTA "Bilarmidingiz," so'zi bilan boshlansin va eng kuchli, shok qiladigan faktni aytsin.
  Masalan: "Bilarmidingiz, sakkizoyoqning uchta yuragi bor!"
- Keyingi gaplarda nega shunday ekanini oddiy tilda tushuntir va 2-3 ta qo'shimcha qiziq detal qo'sh.
- Oxirgi gap tomoshabinni izoh yozishga undovchi qisqa savol bo'lsin (masalan: "Siz buni bilarmidingiz?"). "Obuna bo'ling" deb yozma.
- Gaplar qisqa, ovozda o'qishga qulay. Raqamlarni so'z bilan yoz. Emoji ishlatma.
- Matnni {scenes_min}-{scenes_max} ta sahnaga bo'l (har sahna 1-2 qisqa gap, ~3-5 soniya).
- Har sahna uchun stok VIDEO qidirish uchun 2-4 so'zli INGLIZCHA kalit so'z ber. Kadr HARAKATLI va aynan
  shu gapga mos bo'lsin: "octopus swimming ocean", "rocket launch fire smoke", "cheetah running savanna",
  "blood cells flowing", "lightning storm night sky". Harakatsiz narsalarni ("old book", "stone") tanlama.

Shu faktlar ALLAQACHON ishlatilgan, takrorlama va ularga o'xshatma:
{used}

FAQAT shu JSON formatda javob ber:
{{
  "title": "Qiziqarli sarlavha, 40-70 belgi, faktning eng hayratli qismi bilan",
  "hook": "Ekran tepasidagi 2-4 so'zli qisqa ilmoq matni (masalan: BILARMIDINGIZ?)",
  "scenes": [
    {{"text": "sahnadagi ovozli matn (1-2 gap)", "keywords": "english video search words"}}
  ],
  "description": "2-3 gaplik tavsif: fakt qisqacha va qiziqtiruvchi savol",
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
    # Kanal uslubi: har video "Bilarmidingiz," bilan boshlanadi
    first = scenes[0]["text"]
    if not first.lower().startswith("bilarmidingiz"):
        scenes[0]["text"] = "Bilarmidingiz, " + first[:1].lower() + first[1:]
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
