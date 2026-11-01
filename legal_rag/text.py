"""Turkish text utilities: normalisation, light stemming (first-5-characters), stopwords, sentence split."""
from __future__ import annotations

import re

_FOLD = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "â": "a", "î": "i", "û": "u"})

STOPWORDS = {
    "ve", "veya", "ile", "bir", "bu", "su", "o", "da", "de", "mi", "mu", "ne", "icin", "gibi", "kadar", "nedir",
    "nasil", "hangi", "kac", "en", "az", "olan", "olarak", "ise", "ya", "her", "ben", "benim", "var", "midir",
    "zaman", "zorunda", "gerekir", "yapmali", "edebilirim", "yapabilir", "mudur", "icinde", "sonra", "once",
    "onceden", "haklarim", "almak", "aldim", "aldigim", "etmek", "ederim", "urunu",
}

# Lay terms clients use -> the terms used in the documents. Small, reviewable, owned by the legal team.
SYNONYMS = {
    "ev sahibi": "kiraya veren",
    "mal sahibi": "kiraya veren",
    "fazla mesai": "fazla calisma",
    "internetten": "internet uzerinden",
    "online": "internet uzerinden",
    "bosanmak": "bosanma",
}


def expand_query(text: str) -> str:
    t = normalize(text)
    for lay, term in SYNONYMS.items():
        t = t.replace(lay, term)
    return t


def normalize(text: str) -> str:
    text = text.replace("İ", "i").replace("I", "ı").lower()
    return text.translate(_FOLD)


def stem(token: str) -> str:
    """First-5-characters stemming: a simple, well-known baseline for agglutinative Turkish."""
    return token[:5]


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize(text))


def content_stems(text: str) -> list[str]:
    return [stem(t) for t in tokens(text) if t not in STOPWORDS and (len(t) > 1 or t.isdigit())]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
