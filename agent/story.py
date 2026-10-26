"""Bepul LLM'lar orqali o'zbekcha fakt-video matni + sahnalar + YouTube metadata yaratish.

Bir nechta provayder navbat bilan sinab ko'riladi (Gemini, Groq, Cerebras, OpenRouter, ...).
Qaysi birining kaliti GitHub Secrets'da bo'lsa o'shasi ishlatiladi; band bo'lsa keyingisiga o'tiladi.
"""
import json
import re

import requests

from .utils import env, log, retry

GEMINI = "https://generativelanguage.googleapis.com/v1beta"

# OpenAI-mos bepul provayderlar: nomi -> (kalit o'zgaruvchisi, base url, afzal model andozalari).
# Model nomlari tez-tez yangilanadi, shuning uchun har safar /models ro'yxatidan eng mosini tanlaymiz.
OPENAI_PROVIDERS = {
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1",
             [r"gpt-oss-120b", r"llama.*70b", r"qwen.*(235b|32b|27b)", r"qwen", r"llama"]),
    "cerebras": ("CEREBRAS_API_KEY", "https://api.cerebras.ai/v1",
                 [r"gpt-oss-120b", r"qwen.*235b", r"llama.*70b", r"qwen", r"llama"]),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1",
                   [r"deepseek.*:free$", r"qwen.*:free$", r"llama.*70b.*:free$", r"gemma.*:free$", r":free$"]),
    "mistral": ("MISTRAL_API_KEY", "https://api.mistral.ai/v1",
                [r"^mistral-medium-latest$", r"^mistral-large-latest$", r"^mistral-small-latest$"]),
    "nvidia": ("NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1",
               [r"deepseek-v\d", r"llama.*70b-instruct", r"qwen.*instruct"]),
    "sambanova": ("SAMBANOVA_API_KEY", "https://api.sambanova.ai/v1",
                  [r"deepseek-v\d", r"llama.*70b", r"qwen"]),
}
SKIP_MODELS = re.compile(r"guard|whisper|tts|embed|audio|image|vision|moderation|ocr|rerank|coder|math", re.I)
_model_cache: dict[str, str] = {}

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
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("Javobda JSON topilmadi")
    return json.loads(m.group(0))


# ---------------- Gemini ----------------
def _gemini_models(cfg: dict) -> list[str]:
    """Kalitga ochiq eng yangi Gemini Flash modellar (topilmasa config'dagi ro'yxat)."""
    try:
        r = requests.get(f"{GEMINI}/models", headers={"x-goog-api-key": env("GEMINI_API_KEY")},
                         params={"pageSize": 200}, timeout=20)
        r.raise_for_status()
        names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        flash = [n for n in names if re.fullmatch(r"gemini-[\d.]+-flash(-lite)?", n)]
        flash.sort(key=lambda n: (float(re.search(r"\d+(?:\.\d+)?", n).group(0)), "lite" not in n),
                   reverse=True)
        if flash:
            return flash[:2]
    except Exception as e:  # noqa: BLE001
        log.warning("Gemini modellar ro'yxati olinmadi: %s", e)
    return cfg["gemini"]["models"]


def _call_gemini(model: str, prompt: str, temperature: float) -> str:
    key = env("GEMINI_API_KEY")
    r = requests.post(
        f"{GEMINI}/models/{model}:generateContent",
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


# ---------------- OpenAI-mos provayderlar ----------------
def _pick_model(name: str, base: str, key: str, prefs: list[str]) -> str:
    if name in _model_cache:
        return _model_cache[name]
    r = requests.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
    r.raise_for_status()
    ids = [m["id"] for m in r.json().get("data", []) if not SKIP_MODELS.search(m["id"])]
    if not ids:
        raise RuntimeError(f"{name}: mos model topilmadi")
    chosen = next((mid for pat in prefs for mid in ids if re.search(pat, mid, re.I)), ids[0])
    _model_cache[name] = chosen
    return chosen


def _message_text(data: dict) -> str:
    """OpenAI-uslubidagi javobdan matnni oladi (ba'zi modellar uni boshqa maydonga qo'yadi)."""
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    text = msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning") or ""
    if not text:
        raise RuntimeError(f"Bo'sh javob: {str(data)[:200]}")
    return text


def _call_openai(name: str, prompt: str, temperature: float) -> str:
    var, base, prefs = OPENAI_PROVIDERS[name]
    key = env(var)
    model = _pick_model(name, base, key, prefs)
    log.info("%s modeli: %s", name, model)
    r = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "temperature": temperature,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=90,
    )
    if r.status_code != 200:
        raise RuntimeError(f"{name} {model} HTTP {r.status_code}: {r.text[:300]}")
    return _message_text(r.json())


def _call_pollinations(prompt: str, temperature: float) -> str:
    """Kalitsiz bepul zaxira — boshqa hech biri ishlamasa."""
    r = requests.post(
        "https://text.pollinations.ai/openai",
        json={"model": "openai", "temperature": temperature,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Pollinations HTTP {r.status_code}: {r.text[:300]}")
    return _message_text(r.json())


def _llm_chain(cfg: dict) -> list:
    """Kaliti bor provayderlar config'dagi tartibda: [(nomi, chaqiruvchi funksiya), ...]."""
    order = cfg.get("llm", {}).get("order") or ["gemini", *OPENAI_PROVIDERS, "pollinations"]
    chain = []
    for name in order:
        if name == "gemini":
            if env("GEMINI_API_KEY", required=False):
                for m in _gemini_models(cfg):
                    chain.append((f"gemini/{m}", lambda p, t, m=m: _call_gemini(m, p, t)))
        elif name == "pollinations":
            chain.append((name, _call_pollinations))
        elif name in OPENAI_PROVIDERS and env(OPENAI_PROVIDERS[name][0], required=False):
            chain.append((name, lambda p, t, n=name: _call_openai(n, p, t)))
    return chain


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


@retry(times=2, delay=20)
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
    for label, call in _llm_chain(cfg):
        try:
            log.info("%s matn yozmoqda — mavzu: %s", label, genre)
            raw = call(prompt, cfg["gemini"]["temperature"])
            story = validate(_extract_json(raw), cfg)
            used_lower = {t.lower() for t in used}
            if story["title"].lower() in used_lower:
                raise ValueError("Sarlavha takrorlandi")
            story["genre"] = genre
            story["model"] = label
            history["genre_index"] = gi + 1
            log.info("Matn tayyor (%s): «%s» (%d so'z, %d sahna)",
                     label, story["title"], story["word_count"], len(story["scenes"]))
            return story
        except Exception as e:  # noqa: BLE001
            last_err = e
            log.warning("%s ishlamadi: %s", label, e)
    raise RuntimeError(f"Hech bir model matn bermadi: {last_err}")
