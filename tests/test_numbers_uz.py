import pytest

from agent.numbers_uz import cardinal, ordinal, spoken_numbers


@pytest.mark.parametrize("n,expected", [
    (0, "nol"), (7, "yetti"), (12, "o'n ikki"), (40, "qirq"), (100, "yuz"),
    (270, "ikki yuz yetmish"), (1000, "bir ming"), (1968, "bir ming to'qqiz yuz oltmish sakkiz"),
    (5000, "besh ming"), (2008, "ikki ming sakkiz"), (1_000_000_000, "bir milliard"),
])
def test_cardinal(n, expected):
    assert cardinal(n) == expected


@pytest.mark.parametrize("n,expected", [
    (1, "birinchi"), (2, "ikkinchi"), (5, "beshinchi"), (20, "yigirmanchi"), (1978, "bir ming to'qqiz yuz yetmish sakkizinchi"),
])
def test_ordinal(n, expected):
    assert ordinal(n) == expected


@pytest.mark.parametrize("text,expected", [
    ("1978-yilda Jordan", "bir ming to'qqiz yuz yetmish sakkizinchi yilda Jordan"),
    ("1928 yilda 3 oltin", "bir ming to'qqiz yuz yigirma sakkiz yilda uch oltin"),
    ("5 000 dollar", "besh ming dollar"),
    ("$5000 bilan", "besh ming dollar bilan"),
    ("6,340 km", "olti ming uch yuz qirq km"),
    ("0,5 foizdan", "nol butun o'ndan besh foizdan"),
    ("70% odam", "yetmish foiz odam"),
    ("1973-1974 yillarda", "bir ming to'qqiz yuz yetmish uch - bir ming to'qqiz yuz yetmish to'rt yillarda"),
    ("392 ± 120 yil", "uch yuz to'qson ikki plyus-minus bir yuz yigirma yil".replace("bir yuz", "yuz")),
    ("4x100 metr", "to'rt karra yuz metr"),
    ("Raqamsiz matn.", "Raqamsiz matn."),
])
def test_spoken_numbers(text, expected):
    assert spoken_numbers(text) == expected
