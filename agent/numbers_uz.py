"""Raqamlarni o'zbekcha so'zga aylantirish (faqat ovoz uchun; subtitrda raqam qoladi).

OmniVoice kabi TTS modellari "1968", "5 000", "70%" ni o'qiy olmay tashlab ketadi,
shuning uchun ovozga berishdan oldin matndagi raqamlar so'z bilan yoziladi:
    "1968-yilda 5 000 dollar, 70%"  ->
    "bir ming to'qqiz yuz oltmish sakkizinchi yilda besh ming dollar, yetmish foiz"
"""
import re

ONES = ["nol", "bir", "ikki", "uch", "to'rt", "besh", "olti", "yetti", "sakkiz", "to'qqiz"]
TENS = ["", "o'n", "yigirma", "o'ttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "to'qson"]
SCALES = [(10**12, "trillion"), (10**9, "milliard"), (10**6, "million"), (1000, "ming")]
FRACTION = {1: "o'ndan", 2: "yuzdan", 3: "mingdan"}
VOWELS = set("aeiouAEIOU")


def _below_thousand(n: int) -> list[str]:
    words = []
    hundreds, rest = divmod(n, 100)
    if hundreds:
        words += ([ONES[hundreds]] if hundreds > 1 else []) + ["yuz"]
    tens, ones = divmod(rest, 10)
    if tens:
        words.append(TENS[tens])
    if ones:
        words.append(ONES[ones])
    return words


def cardinal(n: int) -> str:
    """Butun sonni so'z bilan: 1968 -> "bir ming to'qqiz yuz oltmish sakkiz"."""
    if n < 0:
        return "minus " + cardinal(-n)
    if n == 0:
        return ONES[0]
    words = []
    for value, name in SCALES:
        count, n = divmod(n, value)
        if count:
            words += _below_thousand(count) + [name]
    words += _below_thousand(n)
    return " ".join(words)


def ordinal(n: int) -> str:
    """Tartib son: 1 -> "birinchi", 20 -> "yigirmanchi", 1968 -> "... sakkizinchi"."""
    word = cardinal(n)
    return word + ("nchi" if word[-1] in VOWELS else "inchi")


def _decimal(int_part: str, frac_part: str) -> str:
    frac_part = frac_part[:3]
    head = cardinal(int(int_part))
    return f"{head} butun {FRACTION[len(frac_part)]} {cardinal(int(frac_part))}"


# 5 000 / 12 500 000 (bo'sh joy bilan ajratilgan minglar), 6,340 (vergul + aniq 3 raqam), 0,5 / 1.5 (o'nli)
_NUMBER = re.compile(
    r"(?<![\w])"
    r"(?P<num>\d{1,3}(?:[   ]\d{3})+(?!\d)"   # 5 000
    r"|\d{1,3}(?:,\d{3})+(?![\d,])"                      # 6,340
    r"|\d+[.,]\d+"                                         # 0,5  1.5
    r"|\d+)"
    r"(?P<ord>-(?=[^\W\d_]))?"                             # 1978-yilda -> tartib son
)


def _replace(m: re.Match) -> str:
    raw = m.group("num")
    if re.fullmatch(r"\d+[.,]\d+", raw) and not re.fullmatch(r"\d{1,3}(?:,\d{3})+", raw):
        int_part, frac_part = re.split(r"[.,]", raw)
        return _decimal(int_part, frac_part)
    n = int(re.sub(r"[   ,]", "", raw))
    if m.group("ord"):
        return ordinal(n) + " "
    return cardinal(n)


def spoken_numbers(text: str) -> str:
    """Matndagi barcha raqam, foiz, dollar va ± belgilarini o'qiladigan so'zlarga aylantiradi."""
    t = text
    t = re.sub(r"(\d)\s*[x×]\s*(\d)", r"\1 karra \2", t)                 # 4x100
    t = re.sub(r"(\d)\s*±\s*(\d)", r"\1 plyus-minus \2", t)              # 392 ± 120
    t = re.sub(r"\$\s*(\d[\d ,.]*\d|\d)", r"\1 dollar", t)                # $5000 -> 5000 dollar
    t = re.sub(r"(\d)\s*-\s*(\d)", r"\1 - \2", t)                        # 1973-1974 -> oraliq
    t = _NUMBER.sub(_replace, t)
    t = re.sub(r"\s*%", " foiz", t)
    t = re.sub(r"\s*€", " yevro", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()
