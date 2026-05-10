"""Lightweight language detection."""

from __future__ import annotations

from farol._lang import accept_language_for, detect_language


def test_pt_diacritics():
    assert detect_language("imposto de renda 2026 declaração") == "pt"
    assert detect_language("história do Brasil colonial") == "pt"


def test_es_diacritics_and_markers():
    assert detect_language("declaración renta IRPF 2026 España") == "es"
    assert detect_language("modelo 303 IVA trimestral autónomo") == "es"


def test_en():
    assert detect_language("how to deploy fastapi to production") == "en"
    assert detect_language("attention is all you need transformer paper") == "en"


def test_unknown_too_short():
    assert detect_language("") == "unknown"


def test_accept_language_for_query():
    assert "pt-BR" in accept_language_for("imposto de renda")
    assert "es-ES" in accept_language_for("declaración renta")
    assert "en-US" in accept_language_for("python tutorial")


def test_accept_language_for_lang_code():
    assert "pt-BR" in accept_language_for("pt")
    assert "en-US" in accept_language_for("en")
