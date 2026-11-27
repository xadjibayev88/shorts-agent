# apex_wealths — o'z ovozingiz bilan video

Kuniga 1 ta video chiqadi (~14:53 Toshkent vaqti), faqat siz yozib bergan ovoz bilan. Kompyuter ovozi ishlatilmaydi.

## Har kuni nima qilasiz
1. `kutmoqda/` papkasida `NN_nom.txt` fayllari turadi. Yangi ssenariy matni Telegram'ga ham keladi.
2. Matnni telefonda tinch xonada, telefonni og'izdan 15-20 sm uzoqda ushlab o'qing. Raqamlarni so'z bilan ayting.
   45-60 soniya bo'ladi. Xato qilsangiz to'xtab, gapni boshidan qayta o'qing.
3. Yozuvni GitHub'da shu papkaga yuklang: **kutmoqda → Add file → Upload files**.
   Fayl nomi ssenariy raqami bilan boshlansin, masalan `07.m4a`.
   m4a, mp3, ogg (Telegram ovozli xabari), opus, wav, aac va webm fayllari qabul qilinadi.

## Keyin avtomatik
- Shovqin va g'uvillash olinadi, ovoz bir tekis va baland qilinadi, uzun pauzalar qisqartiriladi.
- Subtitr sizning ovozingizga moslanadi (Whisper so'zlarni eshitib vaqtini oladi).
- Kadrlar, musiqa qo'shiladi, YouTube va Instagram'ga joylanadi, fayllar `done/` ga o'tadi.
- Ovoz yuklanmagan kuni video chiqmaydi, Telegram'ga eslatma keladi.

Kompyuter ovoziga qaytish: `config_apex.yaml` da `engine: recorded` o'rniga `engine: edge`.
