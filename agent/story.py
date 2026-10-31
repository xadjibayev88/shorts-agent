"""Bepul LLM'lar orqali o'zbekcha fakt-video matni + sahnalar + YouTube metadata yaratish.

Bir nechta provayder navbat bilan sinab ko'riladi (Gemini, Groq, Cerebras, OpenRouter, ...).
Qaysi birining kaliti GitHub Secrets'da bo'lsa o'shasi ishlatiladi; band bo'lsa keyingisiga o'tiladi.
"""
import json
import re
from datetime import datetime, timezone

import requests

from .utils import env, log, retry

GEMINI = "https://generativelanguage.googleapis.com/v1beta"

# OpenAI-mos bepul provayderlar: nomi -> (kalit o'zgaruvchisi, base url, afzal model andozalari).
# Model nomlari tez-tez yangilanadi, shuning uchun har safar /models ro'yxatidan eng mosini tanlaymiz.
OPENAI_PROVIDERS = {
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1",
             [r"gpt-oss-120b", r"qwen.*(235b|32b|27b)", r"llama.*70b", r"gpt-oss-20b", r"qwen", r"llama"]),
    "cerebras": ("CEREBRAS_API_KEY", "https://api.cerebras.ai/v1",
                 [r"gpt-oss-120b", r"qwen.*235b", r"llama.*70b", r"qwen", r"llama"]),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1",
                   [r"deepseek.*:free$", r"qwen.*:free$", r"llama.*70b.*:free$", r"gemma.*:free$", r":free$"]),
    "mistral": ("MISTRAL_API_KEY", "https://api.mistral.ai/v1",
                [r"^mistral-medium-latest$", r"^mistral-large-latest$", r"^mistral-small-latest$",
                 r"ministral.*14b", r"ministral.*8b", r"ministral"]),
    "nvidia": ("NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1",
               [r"deepseek-v\d", r"llama.*70b-instruct", r"qwen.*instruct"]),
    "sambanova": ("SAMBANOVA_API_KEY", "https://api.sambanova.ai/v1",
                  [r"deepseek-v\d", r"llama.*70b", r"qwen"]),
    "agnes": ("AGNES_API_KEY", "https://apihub.agnes-ai.com/v1",
              [r"agnes.*pro", r"agnes.*flash", r"agnes"]),
    # OmniRoute — workflow ichida ishga tushadigan lokal router; o'zi provayderlar orasida aylanadi
    "omniroute": (None, "http://127.0.0.1:20128/v1", []),
    # Kalitsiz bepul provayderlar (FreeLLMAPI ro'yxatidan) — kalit kerak emas
    "kilo": (None, "https://api.kilo.ai/api/gateway/v1", [r":free$", r"free"]),
    "ovh": (None, "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
            [r"llama.*70b", r"qwen.*(235b|72b|32b)", r"mistral", r"llama"]),
}
SKIP_MODELS = re.compile(r"guard|whisper|tts|embed|audio|image|vision|moderation|ocr|rerank|code|math|allam|robotics|\bvl\b|-vl", re.I)
# /models ro'yxati yopiq yoki keraksiz bo'lgan provayderlar uchun qat'iy modellar
FIXED_MODELS = {"omniroute": ["auto"]}
_model_cache: dict[str, list[str]] = {}

PROMPT = """Sen "Bilarmidingiz" nomli o'zbek tilidagi YouTube Shorts kanali uchun virusli fakt-videolar yozadigan ssenariynavissan.
Kanal yo'nalishi: "{niche}". Bugungi mavzu: {genre}.

VAZIFA: shu mavzu bo'yicha bitta HAQIQIY, ilmiy tasdiqlangan, hayratlanarli faktni tanla va u haqida qisqa video matni yoz.
Talablar:
- Fakt to'qima bo'lmasin. Shubhali, afsonaviy yoki tekshirib bo'lmaydigan faktlarni tanlama. Raqamlar aniq bo'lsin.
- Til: sof, jonli o'zbek tili (lotin yozuvi). O' va G' uchun oddiy apostrof ishlat: o', g'.
- Matn {min_words}-{max_words} so'zdan iborat bo'lsin (ovozda 10-15 soniya). Qisqa video oxirigacha va qayta-qayta ko'riladi — bu Shorts uchun eng muhim ko'rsatkich.
- 1-gap faktning o'zi bo'lsin: ko'pi bilan 7 so'z, 1,5 soniyada aytib bo'linadi, birinchi so'z raqam yoki ekranda ko'rinib turgan narsa.
  Kirish, salomlashish, "bugun sizga", "Bilarmidingiz" YO'Q. Masalan: "Sakkizoyoqning uchta yuragi bor."
- 1-sahna kalit so'zi eng harakatli, yaqin plandagi kadr bo'lsin (masalan: "octopus close up moving").
- Keyingi gaplarda nega shunday ekanini oddiy tilda tushuntir va 1-2 ta qo'shimcha qiziq detal qo'sh. Suv qo'shma: har gap yangi ma'lumot bersin.
- Oxirgi gap 1-gapga qaytib ulansin (loop): video qayta boshlanganda gap davom etayotgandek eshitilsin.
  Oxirgi gap "chunki", "shuning uchun" yoki 1-gapdagi asosiy so'z bilan tugasin. Savol bilan TUGATMA. "Obuna bo'ling" deb yozma.
- Imlo: grammatik jihatdan to'g'ri o'zbekcha yoz, so'z to'qima, inglizcha so'zlarni aralashtirma. Sarlavha ayniqsa xatosiz bo'lsin.
- Gaplar qisqa, ovozda o'qishga qulay. Raqamlarni so'z bilan yoz. Emoji ishlatma.
- Matnni {scenes_min}-{scenes_max} ta sahnaga bo'l (har sahna 1-2 qisqa gap, ~3-5 soniya).
- Har sahna uchun stok VIDEO qidirish uchun 2-4 so'zli INGLIZCHA kalit so'z ber. Kadr HARAKATLI va aynan
  shu gapga mos bo'lsin: "octopus swimming ocean", "rocket launch fire smoke", "cheetah running savanna",
  "blood cells flowing", "lightning storm night sky". Harakatsiz narsalarni ("old book", "stone") tanlama.

Shu faktlar ALLAQACHON ishlatilgan, takrorlama va ularga o'xshatma. Ro'yxatdagi biror sarlavha bilan bir xil asosiy
obyekt (masalan, Rim sementi, Xitoy devori, Venera) bo'lsa, boshqa obyekt tanla:
{used}

FAQAT shu JSON formatda javob ber:
{{
  "title": "Xatosiz o'zbekcha sarlavha, 35-60 belgi, asosiy so'z birinchi 40 belgida (telefonda shuncha ko'rinadi), ko'pi bilan 2 ta KATTA HARFLI so'z: aniq raqam yoki savol bilan (masalan: Sakkizoyoqning nega 3 ta yuragi bor?)",
  "hook": "Ekran tepasidagi 2-4 so'zli, faktning eng shok qismi, KATTA HARFDA (masalan: 3 TA YURAK!). BILARMIDINGIZ so'zini yozma",
  "thumbnail_text": "Muqova uchun 2-3 so'zli KATTA HARFLI yozuv, eng hayratli raqam bilan. Sarlavhadagi so'zlarni TAKRORLAMA — muqova sarlavha aytmagan narsani aytsin (masalan: 3 TA YURAK!)",
  "scenes": [
    {{"text": "sahnadagi ovozli matn (1-2 gap)", "keywords": "english video search words"}}
  ],
  "description": "1-qator: fakt bitta gapda. 2-qator: 'Siz buni bilarmidingiz: A) ha, B) birinchi marta eshitdim? Izohda harf yozing.'",
  "source": "Faktning ishonchli manbasi (masalan: NASA, Britannica, National Geographic, WHO)",
  "tags": ["8-12 ta o'zbekcha va inglizcha teg"],
  "hashtags": ["#3-5", "#ta", "#heshteg"]
}}
"""


MOTIVATION_PROMPT = """Sen "{niche}" yo'nalishidagi o'zbek tilidagi Shorts va Reels kanali uchun ssenariynavissan.
Bugungi mavzu: {genre}.

VAZIFA: shu mavzuda bitta aniq, foydali g'oya tanla va qisqa video matni yoz. Tomoshabin videodan keyin bitta narsani boshqacha qilsin.
Talablar:
- Faqat haqiqiy ma'lumot: mashhur odam, kompaniya yoki raqam keltirsang, u aniq va tekshiriladigan bo'lsin. Iqtibosni faqat muallifi aniq bo'lsa ishlat. To'qima hikoya, soxta statistika, "milliarder bo'lasiz" kabi va'dalar YO'Q.
- Moliyaviy maslahat berma: aniq aksiya, kripto yoki "pul ikki baravar bo'ladi" kabi gaplar yo'q. Odatlar, fikrlash, intizom, biznes saboqlari haqida gapir.
- Til: sof, jonli o'zbek tili (lotin yozuvi). O' va G' uchun oddiy apostrof: o', g'. Inglizcha so'z aralashtirma.
- Matn {min_words}-{max_words} so'z (ovozda 15-25 soniya).
- 1-gap kuchli ilmoq: savol yoki kutilmagan fikr, 10 so'zdan oshmasin. Undov belgisi ishlatma.
- Keyin: nega bu muhim, bitta misol yoki raqam, va bugun qilish mumkin bo'lgan bitta aniq qadam.
- Oxirgi gap ikki variantli tanlov savoli, javobi bitta so'z (masalan: "Siz qaysi birini tanlaysiz: tejash yoki ishlash? Izohda bitta so'z yozing.").
  Ochiq, umumiy savol berma. "Obuna bo'ling" deb yozma.
- Gaplar qisqa, ovozda o'qishga qulay. Raqamlarni so'z bilan yoz. Emoji ishlatma.
- Matnni {scenes_min}-{scenes_max} ta sahnaga bo'l (har sahna 1-2 qisqa gap).
- Har sahna uchun 2-4 so'zli INGLIZCHA stok-video kalit so'z: odam ko'zini uzolmaydigan, harakatli, premium kadr.
  Odamlar ishlayotgan yoki harakatdagi kadrlar, chiroyli yorug'lik, shahar va tabiat dronda ("young man running sunrise",
  "woman working laptop cafe", "city skyline night drone", "hands counting money", "mountain summit hiker", "luxury car night city").
  Har sahna boshqacha kadr bo'lsin, bir xil mavzu takrorlanmasin. Matn so'zma-so'z emas, kayfiyat va ma'noni ko'rsatsin.

Shu sarlavhalar ALLAQACHON ishlatilgan, takrorlama:
{used}

FAQAT shu JSON formatda javob ber:
{{
  "title": "Xatosiz o'zbekcha sarlavha, 35-60 belgi, undov belgisisiz",
  "hook": "Ekran tepasidagi 2-4 so'zli KATTA HARFLI yozuv",
  "thumbnail_text": "Muqova uchun 2-3 so'zli KATTA HARFLI yozuv, sarlavhani takrorlamasin",
  "scenes": [
    {{"text": "sahnadagi ovozli matn (1-2 gap)", "keywords": "english video search words"}}
  ],
  "description": "2-3 gaplik tavsif",
  "source": "Ishlatilgan fakt yoki iqtibosning manbasi (kitob, muallif, nashr); faktsiz bo'lsa: Umumiy maslahat",
  "tags": ["8-12 ta o'zbekcha va inglizcha teg"],
  "hashtags": ["#3-5", "#ta", "#heshteg"]
}}
"""

PROMPTS = {"facts": PROMPT, "motivation": MOTIVATION_PROMPT}


def _word_count(s: str) -> int:
    return len(re.findall(r"\w[\w']*", s))


def _extract_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("Javobda JSON topilmadi")
    blob = m.group(0)
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        # Modellar ko'pincha oxirgi elementdan keyin vergul qoldiradi
        return json.loads(re.sub(r",\s*([}\]])", r"\1", blob))


# ---------------- Gemini ----------------
def _gemini_models(cfg: dict) -> list[str]:
    """Kalitga ochiq Gemini/Gemma modellar: eng yangi Flash'lar, Gemma 4, keyin Flash-Lite."""
    try:
        r = requests.get(f"{GEMINI}/models", headers={"x-goog-api-key": env("GEMINI_API_KEY")},
                         params={"pageSize": 200}, timeout=20)
        r.raise_for_status()
        names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]

        def ver(n: str) -> float:
            return float(re.search(r"\d+(?:\.\d+)?", n).group(0))

        flash = [n for n in names if re.fullmatch(r"gemini-[\d.]+-flash(-preview)?", n)]
        lite = [n for n in names if re.fullmatch(r"gemini-[\d.]+-flash-lite(-preview)?", n)]
        gemma = [n for n in names if re.fullmatch(r"gemma-\d+-\d+b-it", n)]
        flash.sort(key=ver, reverse=True)
        lite.sort(key=ver, reverse=True)
        gemma.sort(key=lambda n: (ver(n), int(re.search(r"(\d+)b", n).group(1))), reverse=True)
        models = flash[:3] + gemma[:2] + lite[:1]
        if models:
            return models
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


def _call_gemini_search(model: str, prompt: str) -> tuple[str, list[dict]]:
    """Gemini + Google Search: model javobdan oldin internetdan qidiradi. (matn, manbalar) qaytaradi."""
    r = requests.post(
        f"{GEMINI}/models/{model}:generateContent",
        headers={"x-goog-api-key": env("GEMINI_API_KEY"), "Content-Type": "application/json"},
        # Qidiruv vositasi JSON rejimi bilan birga ishlamaydi, shuning uchun JSON'ni matndan ajratamiz
        json={"contents": [{"role": "user", "parts": [{"text": prompt}]}],
              "tools": [{"google_search": {}}],
              "generationConfig": {"temperature": 0.1}},
        timeout=120,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Gemini qidiruv {model} HTTP {r.status_code}: {r.text[:300]}")
    cand = r.json()["candidates"][0]
    text = "".join(p.get("text", "") for p in cand["content"]["parts"] if not p.get("thought"))
    chunks = (cand.get("groundingMetadata") or {}).get("groundingChunks") or []
    sources = [c["web"] for c in chunks if c.get("web", {}).get("uri")]
    return text, sources


# ---------------- OpenAI-mos provayderlar ----------------
def _pick_models(name: str, base: str, key: str, prefs: list[str], limit: int = 3) -> list[str]:
    """Provayderning /models ro'yxatidan afzal andozalarga mos eng yaxshi bir nechta model."""
    if name in FIXED_MODELS:
        return FIXED_MODELS[name]
    if name in _model_cache:
        return _model_cache[name]
    r = requests.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"} if key else {}, timeout=20)
    r.raise_for_status()
    ids = [m["id"] for m in r.json().get("data", []) if not SKIP_MODELS.search(m["id"])]
    if not ids:
        raise RuntimeError(f"{name}: mos model topilmadi")
    chosen = []
    for pat in prefs:
        for mid in ids:
            if mid not in chosen and re.search(pat, mid, re.I):
                chosen.append(mid)
    chosen = (chosen or ids)[:limit]
    _model_cache[name] = chosen
    return chosen


def _message_text(data: dict) -> str:
    """OpenAI-uslubidagi javobdan matnni oladi (ba'zi modellar uni boshqa maydonga qo'yadi)."""
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    text = msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning") or ""
    if not text:
        raise RuntimeError(f"Bo'sh javob: {str(data)[:200]}")
    return text


def _call_openai(name: str, model: str, prompt: str, temperature: float) -> str:
    var, base, _prefs = OPENAI_PROVIDERS[name]
    key = env(var) if var else ""
    r = requests.post(
        f"{base}/chat/completions",
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})},
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
    """Kaliti bor provayderlarning barcha mos modellari, config'dagi tartibda: [(nomi, funksiya), ...]."""
    order = cfg.get("llm", {}).get("order") or ["gemini", *OPENAI_PROVIDERS, "pollinations"]
    chain = []
    for name in order:
        if name == "gemini":
            if env("GEMINI_API_KEY", required=False):
                for m in _gemini_models(cfg):
                    chain.append((f"gemini/{m}", lambda p, t, m=m: _call_gemini(m, p, t)))
        elif name == "pollinations":
            chain.append((name, _call_pollinations))
        elif name in OPENAI_PROVIDERS:
            var, base, prefs = OPENAI_PROVIDERS[name]
            key = env(var, required=False) if var else ""
            if var and not key:
                continue
            try:
                models = _pick_models(name, base, key, prefs)
            except Exception as e:  # noqa: BLE001
                log.warning("%s modellar ro'yxati olinmadi: %s", name, e)
                continue
            for m in models:
                chain.append((f"{name}/{m}", lambda p, t, n=name, m=m: _call_openai(n, m, p, t)))
    log.info("Model zanjiri (%d ta): %s", len(chain), ", ".join(label for label, _ in chain))
    return chain


def clean_title(title: str) -> str:
    """Sarlavha darvozasi (analitika 2026-10-31): "!" va KATTA so'zli sarlavhalar mediana 6-9 ko'rish olgan.

    Undov, qo'shtirnoq va #teglarni olib tashlaydi, 4+ harfli KATTA so'zlarni oddiy yozuvga o'tkazadi,
    60 belgidan uzun bo'lsa so'z chegarasida qisqartiradi.
    """
    t = re.sub(r"#\w+", "", title or "")
    t = re.sub(r"[!\"“”«»]", "", t)
    keep = {"NASA", "UNESCO", "NATO", "AQSH", "YUNESKO", "FIFA", "BMT"}
    t = re.sub(r"\b(\w*[A-Z]{4,}\w*)\b", lambda m: m.group(1) if m.group(1) in keep else m.group(1).capitalize(), t)
    t = re.sub(r"\s+", " ", t).strip(" -–—:")
    if len(t) > 60:
        t = t[:60].rsplit(" ", 1)[0].rstrip(" ,-–—:")
    return t[:1].upper() + t[1:] if t else "Qiziqarli fakt"


def validate(story: dict, cfg: dict, strict_words: bool = True) -> dict:
    sc = cfg["story"]
    scenes = [s for s in story.get("scenes", []) if s.get("text", "").strip()]
    if len(scenes) < 3:
        raise ValueError(f"Sahnalar juda kam: {len(scenes)}")
    for s in scenes:
        s["text"] = re.sub(r"\s+", " ", s["text"]).strip()
        s["keywords"] = (s.get("keywords") or "nature landscape").strip()
    # Kanal uslubi: har video bir xil so'z bilan boshlanadi (config: story.opener, bo'sh = yo'q)
    opener = cfg["story"].get("opener", "Bilarmidingiz")
    first = scenes[0]["text"]
    if opener and not first.lower().startswith(opener.lower()):
        scenes[0]["text"] = f"{opener}, " + first[:1].lower() + first[1:]
    words = sum(_word_count(s["text"]) for s in scenes)
    if strict_words and not (sc["min_words"] * 0.7 <= words <= sc["max_words"] * 1.2):
        raise ValueError(f"So'z soni mos emas: {words}")
    story["scenes"] = scenes
    story["title"] = clean_title(story.get("title", "Qiziqarli hikoya"))
    story["hook"] = (story.get("hook") or "").strip()[:40]
    # Har videoda bir xil "BILARMIDINGIZ?" ilmog'i e'tiborni tortmaydi — o'rniga faktning o'zi
    if not story["hook"] or (opener and opener.lower() in story["hook"].lower()):
        story["hook"] = (story.get("thumbnail_text") or story["title"]).strip()[:40]
    story["thumbnail_text"] = (story.get("thumbnail_text") or story["hook"] or story["title"]).strip()[:60]
    story["tags"] = [t.strip("# ").strip() for t in story.get("tags", []) if t.strip()][:15]
    story["hashtags"] = [h if h.startswith("#") else f"#{h}" for h in story.get("hashtags", [])][:5]
    story["description"] = story.get("description", "").strip()
    source = (story.get("source") or "").strip()
    if source and "Manba:" not in story["description"]:
        story["description"] = f"{story['description']}\n\nManba: {source[:120]}".strip()
    story["word_count"] = words
    return story


VERIFY_PROMPT = """Sen qat'iy fakt-tekshiruvchisan. Quyidagi o'zbekcha qisqa video matnidagi har bir faktni va raqamni tekshir.
Bugungi sana: {today}. Fakt shu sanaga to'g'ri bo'lsin: yangi kashfiyot, rekord yoki o'zgarish bilan eskirgan bo'lsa "false" de.
Matn:
{text}

Agar barcha asosiy faktlar va raqamlar haqiqatga to'g'ri kelsa "true", biror muhim fakt noto'g'ri, bo'rttirilgan
yoki to'qima bo'lsa "false", ishonchli bilmasang "uncertain" de. "Umrbod", "yagona", "hamma" kabi mutlaq
da'volarga ayniqsa qattiq qara. Matndagi har bir nom (odam, joy, hayvon, inshoot, atama) haqiqatda
mavjudligini tekshir: to'qima, buzilgan yoki ma'nosiz nom/so'z bo'lsa (sarlavhada ham) "false" de.
Maslahat, fikr va motivatsion gaplar ("bugun eng muhim ishdan boshlang", "kichik ishlar charchatadi") fakt emas:
ularni hukmga qo'shma. Faqat tekshiriladigan da'volarni baholab: nomlar, raqamlar, sanalar, kim nima qilgan yoki degan.
Mashhur qoida yoki tamoyilni o'z nomi bilan aytish (masalan, "80/20 qoidasi") noto'g'ri emas.
Xorijiy ismlar o'zbek lotin imlosida yoziladi va bu XATO EMAS: "Uorren Baffet" = Warren Buffett, "Devid Allen" = David Allen,
"Dayson" = James Dyson, "Jeff Bezos", "Kerolin Devidson" = Carolyn Davidson. Ismni asl inglizcha shakliga solishtirib tekshir,
faqat butunlay boshqa odam yoki to'qima ism bo'lsa "false" de.
Avval har bir da'voni qisqa tekshir, keyin hukm chiqar.
FAQAT shu JSON formatda javob ber:
{{"issues": "har bir asosiy da'vo bo'yicha 1-2 gapli tekshiruv", "verdict": "true | false | uncertain"}}
"""


class FactError(ValueError):
    """Tekshiruvchi faktni tasdiqlamadi; xabarda uning izohi bor."""


FIX_PROMPT = """Quyidagi video matni fakt-tekshiruvdan o'tmadi. Tekshiruvchi izohi:
{issues}

Xatolarni tuzat: noto'g'ri yoki shubhali faktlarni olib tashla yoki aniq, tasdiqlangan ma'lumot bilan almashtir.
Boshqa barcha talablar o'zgarmaydi. Asl topshiriq:
{prompt}

Avvalgi matn (JSON):
{story}

FAQAT tuzatilgan to'liq JSON bilan javob ber.
"""


TEMPLATE_ECHO = ("har bir asosiy da'vo bo'yicha", "har bir nom haqiqatda mavjud")


def _usable(issues: str) -> bool:
    """Tekshiruvchi haqiqatan tekshirganmi: juda qisqa yoki shablonni qaytargan javob ovoz emas."""
    low = issues.lower()
    return len(issues) >= 25 and not any(t in low for t in TEMPLATE_ECHO)


def _verdict(res: dict, label: str, story: dict) -> bool:
    """Tekshiruvchi javobini baholaydi. True = qabul, False = javob yaroqsiz (keyingisiga o'tamiz)."""
    verdict = str(res.get("verdict", "")).lower().strip()
    if not _usable(str(res.get("issues", ""))):
        log.warning("Tekshiruvchi %s izohsiz javob berdi — keyingisiga o'tamiz", label)
        return False
    log.info("Fakt tekshiruvi (%s): %s — %s", label, verdict, str(res.get("issues", ""))[:200])
    if verdict != "true":
        raise FactError(f"Fakt tasdiqlanmadi ({label}): {res.get('issues', '')}"[:300])
    story["verified_by"] = label
    return True


def _fact_check(story: dict, chain: list, author: str, cfg: dict) -> None:
    """Fakt-tekshiruv. Avval Gemini Google Search bilan internetdan, bo'lmasa BOSHQA provayderdagi model.

    Tasdiqlanmasa FactError. Hech bir tekshiruvchi ishlamasa va fact_check.required bo'lsa —
    RuntimeError: tekshirilmagan video joylanmaydi.
    """
    fc = cfg.get("fact_check", {})
    provider = author.split("/")[0]
    text = (f"Sarlavha: {story['title']}\nEkrandagi yozuv: {story.get('hook', '')}\n"
            f"Muqova: {story.get('thumbnail_text', '')}\n" + " ".join(s["text"] for s in story["scenes"]))
    prompt = VERIFY_PROMPT.format(text=text, today=datetime.now(timezone.utc).date().isoformat())

    # 1) Internet bilan tekshiruv (Gemini + Google Search) — eskirgan faktlarni ham ushlaydi
    if fc.get("web_search", True) and env("GEMINI_API_KEY", required=False):
        for model in _gemini_models(cfg)[:3]:
            label = f"gemini-search/{model}"
            try:
                raw, sources = _call_gemini_search(model, prompt)
                res = _extract_json(raw)
            except Exception as e:  # noqa: BLE001
                log.warning("Tekshiruvchi %s ishlamadi: %s", label, e)
                continue
            if not sources:
                log.warning("Tekshiruvchi %s internetdan qidirmadi — keyingisiga o'tamiz", label)
                continue
            if _verdict(res, label, story):
                story["fact_sources"] = [{"title": s.get("title", ""), "uri": s["uri"]} for s in sources[:5]]
                return

    # 2) Zaxira: boshqa provayderlardagi modellar (internetsiz, o'z bilimi bilan).
    # Bitta model adashishi mumkin, shuning uchun ko'pchilik ovozi: 2 ta bir xil hukm yetarli, aks holda 3-chisi hal qiladi.
    # OmniRoute birinchi: u o'zi tirik provayderni tanlaydi, band Gemini'ni kutib o'tirmaymiz
    verifiers = sorted(chain, key=lambda c: not c[0].startswith("omniroute/"))
    votes: list[tuple[str, bool, str]] = []
    seen: set[str] = set()
    for label, call in verifiers:
        prov = label.split("/")[0]
        if prov in (provider, "pollinations") or prov in seen:
            continue
        try:
            res = _extract_json(call(prompt, 0.1))
        except Exception as e:  # noqa: BLE001
            log.warning("Tekshiruvchi %s ishlamadi: %s", label, e)
            continue
        issues = str(res.get("issues", ""))
        if not _usable(issues):
            log.warning("Tekshiruvchi %s izohsiz javob berdi — keyingisiga o'tamiz", label)
            continue
        ok = str(res.get("verdict", "")).lower().strip() == "true"
        log.info("Fakt tekshiruvi (%s): %s — %s", label, "true" if ok else "false", issues[:200])
        seen.add(prov)
        votes.append((label, ok, issues))
        yes = sum(v[1] for v in votes)
        no = len(votes) - yes
        if yes >= 2:
            story["verified_by"] = ", ".join(v[0] for v in votes if v[1])
            return
        if no >= 2:
            bad = "; ".join(f"{v[0]}: {v[2]}" for v in votes if not v[1])
            raise FactError(f"Fakt tasdiqlanmadi (ko'pchilik ovozi): {bad}"[:400])
    if votes and len(votes) < 2:
        # Faqat bitta tekshiruvchi javob berdi: ehtiyot uchun uning hukmiga amal qilamiz
        label, ok, issues = votes[0]
        if ok:
            story["verified_by"] = label
            return
        raise FactError(f"Fakt tasdiqlanmadi ({label}): {issues}"[:300])

    if fc.get("required", True):
        raise RuntimeError("Hech bir fakt-tekshiruvchi ishlamadi — tekshirilmagan video joylanmaydi")
    log.warning("Tekshiruvchi model topilmadi — fakt tekshirilmadi")


@retry(times=2, delay=20)
def generate_story(cfg: dict, history: dict) -> dict:
    genres = cfg["channel"]["genres"]
    gi = history.get("genre_index", 0) % len(genres)
    genre = genres[gi]
    used = [v["title"] for v in history.get("videos", [])][-cfg["story"]["history_avoid_last"]:]
    template = PROMPTS.get(cfg["story"].get("style", "facts"), PROMPT)
    prompt = template.format(
        niche=cfg["channel"]["niche"], genre=genre,
        min_words=cfg["story"]["min_words"], max_words=cfg["story"]["max_words"],
        scenes_min=cfg["story"]["scenes_min"], scenes_max=cfg["story"]["scenes_max"],
        used="\n".join(f"- {t}" for t in used) or "- (hali yo'q)",
    )
    last_err = None
    chain = _llm_chain(cfg)
    for label, call in chain:
        try:
            log.info("%s matn yozmoqda — mavzu: %s", label, genre)
            raw = call(prompt, cfg["gemini"]["temperature"])
            story = validate(_extract_json(raw), cfg)
            used_lower = {t.lower() for t in used}
            if story["title"].lower() in used_lower:
                raise ValueError("Sarlavha takrorlandi")
            try:
                _fact_check(story, chain, label, cfg)
            except FactError as fe:
                # Tashlab yubormaymiz: muallif model tekshiruvchi izohi bo'yicha bir marta tuzatadi
                log.info("%s matnni tuzatmoqda: %s", label, fe)
                draft = {k: story[k] for k in ("title", "hook", "thumbnail_text", "scenes", "source") if k in story}
                raw = call(FIX_PROMPT.format(issues=fe, prompt=prompt,
                                             story=json.dumps(draft, ensure_ascii=False)), 0.4)
                story = validate(_extract_json(raw), cfg)
                _fact_check(story, chain, label, cfg)
            # Tavsifga internetda topilgan manbalarni qo'shamiz (Gemini havolalari vaqtinchalik, shuning uchun sayt nomi)
            sites = list(dict.fromkeys(s["title"] for s in story.get("fact_sources", []) if s.get("title")))[:3]
            if sites:
                story["description"] += "\nTekshirildi: " + ", ".join(sites)
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
