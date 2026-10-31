# 🎬 YouTube Shorts Agent (o'zbekcha qisqa hikoyalar)

Har kuni **3 marta** o'zi ishga tushadi va to'liq avtomatik:

1. **Gemini AI** — original o'zbekcha qisqa hikoya yozadi (hook → taranglik → burilish), sarlavha, tavsif, teglar bilan. Janrlar navbat bilan almashadi, sarlavhalar takrorlanmaydi.
2. **Edge TTS** — o'zbekcha tabiiy ovoz (Sardor yoki Madina), bepul.
3. **Pexels** — har sahnaga mos vertikal stok video (bir xil kadr qayta ishlatilmaydi).
4. **ffmpeg montaj** — 1080×1920, sekin kamera harakati, so'zma-so'z yonadigan karaoke subtitrlar, tepada HOOK matni, pastda progress bar, fon musiqasi (ovoz paytida avtomatik pasayadi), ovoz balandligi -14 LUFS.
5. **YouTube API** — #shorts bilan joylaydi, AI-kontent belgisini qo'yadi.
6. **Telegram** (ixtiyoriy) — har video joylanganda sizga xabar yuboradi.

Hammasi **GitHub Actions**'da bepul ishlaydi — kompyuteringiz yoqilgan bo'lishi shart emas.

---

## ⚙️ O'rnatish (bir marta, ~30 daqiqa)

### 1. GitHub repozitoriya
GitHub'da yangi **Private** repo oching va shu papkadagi barcha fayllarni yuklang (`.github` papkasi ham!).

### 2. Gemini API kaliti (bepul)
https://aistudio.google.com/apikey → **Create API key** → nusxalang.

### 3. Pexels API kaliti (bepul)
https://www.pexels.com/api/ → ro'yxatdan o'ting → API key oling.

### 4. YouTube ruxsati (eng muhim qadam)
1. https://console.cloud.google.com → yangi loyiha yarating.
2. **APIs & Services → Library** → "YouTube Data API v3" → **Enable**.
3. **OAuth consent screen** → External → ilova nomi, emailingiz → saqlang.
   - **Audience / Test users** ga o'z Gmail'ingizni qo'shing.
   - ⚠️ So'ng **Publish app** (In production) tugmasini bosing. Aks holda token **7 kunda** eskiradi va agent to'xtaydi.
4. **Credentials → Create credentials → OAuth client ID → Desktop app** → JSON'ni `client_secret.json` nomi bilan yuklab oling.
5. O'z kompyuteringizda:
   ```bash
   pip install google-auth-oauthlib
   python get_token.py client_secret.json
   ```
   Brauzerda kanalingiz akkauntini tanlang ("Google hasn't verified this app" chiqsa → Advanced → Go to ... → Allow). Terminalda 3 ta qiymat chiqadi.

### 5. GitHub Secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Nomi | Qiymat |
|---|---|
| `GEMINI_API_KEY` | 2-qadamdagi kalit |
| `PEXELS_API_KEY` | 3-qadamdagi kalit |
| `YT_CLIENT_ID` | get_token.py natijasi |
| `YT_CLIENT_SECRET` | get_token.py natijasi |
| `YT_REFRESH_TOKEN` | get_token.py natijasi |
| `TELEGRAM_BOT_TOKEN` | *(ixtiyoriy)* @BotFather'dan |
| `TELEGRAM_CHAT_ID` | *(ixtiyoriy)* sizning chat ID |

### 6. Sinov
Repo → **Actions** → "YouTube Shorts Agent" → **Run workflow** → `upload = false` → ishga tushiring.
Tugagach, pastdagi **Artifacts**'dan videoni yuklab ko'ring. Yoqsa — `upload = true` bilan qayta ishga tushiring. Shundan keyin jadval bo'yicha o'zi ishlaydi.

---

## ⚠️ Bilish shart bo'lgan 2 ta cheklov

**1. YouTube API auditi.** 2020-yildan keyin yaratilgan, tekshiruvdan o'tmagan Google Cloud loyihalari orqali yuklangan videolar YouTube tomonidan avtomatik **Private (yopiq)** qilib qo'yiladi. Videolar ochiq chiqishi uchun bepul **"YouTube API Services – Audit and Quota Extension"** formasini to'ldiring (Google'da shu nom bilan qidiring). Javob odatda bir necha kundan bir necha haftagacha keladi. Shu orada videolarni YouTube Studio'da qo'lda Public qilishingiz mumkin.

**2. Kunlik kvota.** Bepul kvota 10 000 birlik, bitta yuklash ≈ 1 600 birlik → kuniga **maksimal 6 ta**. Jadvalda 3 ta (≈4 800 birlik), zaxira qoldirilgan. Ko'proq kerak bo'lsa, o'sha audit formasida kvota oshirishni so'rang.

---

## 🎛 Sozlash (`config.yaml`)

- **Janrlar** — `channel.genres` ro'yxatini o'zgartiring.
- **Ovoz** — `tts.voice`: `uz-UZ-SardorNeural` (erkak) yoki `uz-UZ-MadinaNeural` (ayol); `rate` — tezlik.
- **Vaqtlar** — `.github/workflows/shorts.yml` dagi `cron` qatorlari (UTC; Toshkent = UTC+5).
- **Musiqa** — `assets/music/` ga royalty-free `.mp3` tashlang (YouTube Audio Library'dan). Bo'sh bo'lsa musiqasiz ishlaydi.
- **Subtitr** — `subtitles` bo'limi: shrift o'lchami, rangi, qatordagi so'zlar soni.

## 💻 Kompyuterda ishlatish (ixtiyoriy)
```bash
pip install -r requirements.txt   # + ffmpeg o'rnatilgan bo'lsin
export GEMINI_API_KEY=... PEXELS_API_KEY=...
python -m agent.main --no-upload                              # faqat video
python -m agent.main --story samples/sample_story.json --no-upload   # Gemini'siz sinov
```

## 💡 Kanal o'sishi uchun maslahat
- YouTube bir xil shablondagi takroriy kontentni monetizatsiyadan chiqarishi mumkin. Shuning uchun janrlarni ko'paytiring, vaqti-vaqti bilan `config.yaml`dagi prompt va ovozni almashtiring.
- Birinchi 2 haftada qaysi janr ko'proq ko'rilayotganini kuzating va `genres` ro'yxatida o'shalarni ko'paytiring.
