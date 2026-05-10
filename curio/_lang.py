"""Lightweight language detection — heuristic, zero deps, fast.

Used to set Accept-Language headers and to bias the router slightly toward
sites tagged with the same language. Not perfect, just useful: distinguishes
PT / ES / EN / FR / DE / IT well enough for routing.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

_PT_MARKERS = {
    # function words and common content words
    "de", "do", "da", "dos", "das", "no", "na", "nos", "nas",
    "que", "uma", "uns", "para", "como", "com", "mais", "ou",
    "não", "está", "são", "também", "você", "três", "depois", "muito",
    "isso", "esse", "essa", "fazer", "tem", "porque", "através",
    # very-PT content words / domain
    "história", "biografia", "geografia", "política", "saúde",
    "imposto", "renda", "tributação", "tributário", "fiscal",
    "previdenciário", "regulação", "código", "lei", "ministério",
    "brasil", "brasileira", "brasileiro", "português",
    "decreto", "decisão", "secretaria", "ministra", "presidente",
    "futebol", "samba", "feijoada", "açúcar", "pão",
    "começar", "começo", "começar",
}
_ES_MARKERS = {
    # function words
    "el", "la", "los", "las", "un", "una", "y", "que", "para",
    "como", "más", "también", "del", "al", "se", "no",
    # diacritics-only ES
    "español", "españa", "está", "qué", "cómo", "cuándo",
    "dónde", "quién", "según", "después", "días", "años",
    # domain
    "tributación", "renta", "modelo", "hacienda", "autónomo",
    "ahorro", "cuenta", "cuota", "tarifa", "vivienda", "deducción",
    "criptomonedas", "presidente", "ministro", "decreto",
    "historia", "biografía", "literatura", "música",
    "fútbol", "paella", "tortilla", "flamenco",
}
_EN_MARKERS = {
    # function words
    "the", "and", "of", "for", "with", "to", "in", "on", "at", "by",
    "is", "are", "was", "were", "be", "been", "this", "that",
    "what", "how", "why", "where", "when", "who",
    "you", "your", "us", "we", "they", "their",
    "all", "any", "some", "more", "most", "best", "good",
    "tutorial", "explained", "guide", "review", "comparison",
    # domain
    "tax", "deduction", "irs", "hmrc", "vat", "ein", "401k",
    "history", "biography", "anatomy", "evolution",
    "recipe", "workout", "wine", "league", "season",
    "transformer", "paper", "model", "framework",
}
_FR_MARKERS = {"le", "la", "les", "des", "ç", "déclaration", "impôt", "français", "français"}
_IT_MARKERS = {"il", "gli", "tasse", "imposte", "dichiarazione", "italiano"}
_DE_MARKERS = {"der", "die", "das", "und", "steuer", "erklärung", "deutsch"}

_TOKEN = re.compile(r"\w+", re.UNICODE)


def detect_language(text: str) -> str:
    """Return ``"pt"``, ``"es"``, ``"en"``, ``"fr"``, ``"de"``, ``"it"``, or ``"unknown"``."""
    text = (text or "").strip().lower()
    if not text:
        return "unknown"

    # Diacritic-based fast path.
    if "ção" in text or "ções" in text or "ões" in text:
        return "pt"
    if "ñ" in text:
        return "es"

    tokens = set(_TOKEN.findall(text))

    score = Counter()
    score["pt"] = len(tokens & _PT_MARKERS) + (2 if any("ç" in t for t in tokens) else 0)
    score["es"] = len(tokens & _ES_MARKERS)
    score["en"] = len(tokens & _EN_MARKERS)
    score["fr"] = len(tokens & _FR_MARKERS)
    score["it"] = len(tokens & _IT_MARKERS)
    score["de"] = len(tokens & _DE_MARKERS)

    # Tie-break: ASCII-only with EN markers → en. With unicode accents → pt or es.
    has_diacritics = any(unicodedata.category(c) == "Mn" for c in unicodedata.normalize("NFD", text))
    if not has_diacritics and score["en"] > 0 and score["en"] >= score.most_common(1)[0][1]:
        return "en"

    best, n = score.most_common(1)[0]
    if n == 0:
        return "unknown"
    return best


_ACCEPT_LANG = {
    "pt": "pt-BR,pt;q=0.9,en;q=0.5",
    "es": "es-ES,es;q=0.9,en;q=0.5",
    "en": "en-US,en;q=0.9",
    "fr": "fr-FR,fr;q=0.9,en;q=0.5",
    "de": "de-DE,de;q=0.9,en;q=0.5",
    "it": "it-IT,it;q=0.9,en;q=0.5",
    "unknown": "en-US,en;q=0.9,pt;q=0.6,es;q=0.6",
}


def accept_language_for(text_or_lang: str) -> str:
    """Return an Accept-Language header value for a query string OR a language code."""
    val = text_or_lang
    if len(val) > 5 or " " in val:
        val = detect_language(val)
    return _ACCEPT_LANG.get(val, _ACCEPT_LANG["unknown"])


__all__ = ["accept_language_for", "detect_language"]
