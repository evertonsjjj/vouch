"""Lightweight CPU-only OCR for text CAPTCHAs via Tesseract.

Why Tesseract instead of a vision LLM
-------------------------------------
For the typical "distorted text" CAPTCHA seen on government / legal /
academic sites (Receita Federal, CVM, Jusbrasil, agencia tributaria,
gov.uk), a small classical OCR engine is plenty:

* **Tiny footprint**: ``pytesseract`` is a 100 KB Python wrapper; the
  Tesseract binary itself is ~30 MB on disk and runs entirely on CPU.
* **Fast**: 50-200 ms per image vs 2-8 s for a local vision LLM.
* **Predictable**: deterministic, no token budgets, no GPU drama.
* **Cheap**: $0, no API key, no model download.

A vision LLM (qwen2.5-vl, llama3.2-vision, …) is still needed for
**image-grid CAPTCHAs** ("select all squares with traffic lights"),
which Tesseract obviously cannot solve. The :class:`CaptchaSolver`
chains them automatically: text → Tesseract, fall back to vision LLM
on low confidence; image grid → vision LLM only.

Install
-------
::

    pip install 'farol[ocr]'    # pytesseract wrapper
    # plus the system binary:
    #   Ubuntu/Debian: sudo apt install tesseract-ocr tesseract-ocr-por tesseract-ocr-spa
    #   macOS:         brew install tesseract tesseract-lang
    #   Windows:       https://github.com/UB-Mannheim/tesseract/wiki

The Portuguese + Spanish language packs are optional but recommended for
BR / ES CAPTCHAs (many gov sites embed locale-aware glyphs).
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import TYPE_CHECKING

from .solver import CaptchaResult

if TYPE_CHECKING:
    pass

log = logging.getLogger("farol.captcha.tesseract")


def is_available() -> bool:
    """Return True if both pytesseract and the tesseract binary are usable."""
    try:
        import pytesseract  # type: ignore
    except ImportError:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def solve_text(
    image: bytes,
    *,
    lang: str = "eng+por+spa",
    min_confidence: float = 0.55,
    whitelist: str | None = None,
) -> CaptchaResult:
    """Try to read distorted text from ``image`` via Tesseract.

    Parameters
    ----------
    image
        Raw bytes of a PNG/JPEG/BMP image containing the CAPTCHA text.
    lang
        Tesseract language string (``"eng+por+spa"`` chains three packs).
        Falls back to ``"eng"`` if the others aren't installed.
    min_confidence
        Below this, the result is marked unsolved (``solved=False``) so the
        caller can escalate to a vision LLM.
    whitelist
        Optional character whitelist (e.g. ``"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"``)
        — speeds up Tesseract dramatically on alphanumeric CAPTCHAs.
    """
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError as e:
        return CaptchaResult(
            solved=False,
            kind="text",
            reason=f"OCR deps missing: {e}. Install with: pip install 'farol[ocr]'",
        )

    try:
        img = Image.open(BytesIO(image))
    except Exception as e:
        return CaptchaResult(solved=False, kind="text", reason=f"image_open_failed: {e}")

    config = "--psm 8"  # single word / line — what CAPTCHAs almost always are
    if whitelist:
        config += f" -c tessedit_char_whitelist={whitelist}"

    # Use image_to_data so we get per-token confidence scores.
    try:
        data = pytesseract.image_to_data(
            img, lang=lang, config=config, output_type=pytesseract.Output.DICT
        )
    except pytesseract.TesseractNotFoundError as e:
        return CaptchaResult(
            solved=False,
            kind="text",
            reason=f"tesseract binary missing: {e}",
        )
    except pytesseract.TesseractError as e:
        # Likely the requested language pack isn't installed. Retry with eng only.
        log.info("Tesseract complained (%s); retrying with lang='eng'", e)
        try:
            data = pytesseract.image_to_data(
                img, lang="eng", config=config, output_type=pytesseract.Output.DICT
            )
        except Exception as e2:
            return CaptchaResult(solved=False, kind="text", reason=f"tesseract_failed: {e2}")

    words = [w for w in (data.get("text") or []) if w and w.strip()]
    confs = []
    for c in data.get("conf") or []:
        try:
            cf = float(c)
            if cf >= 0:
                confs.append(cf / 100.0)
        except (TypeError, ValueError):
            continue

    text = "".join(words).strip()
    confidence = sum(confs) / len(confs) if confs else 0.0

    return CaptchaResult(
        solved=bool(text) and confidence >= min_confidence,
        text=text,
        confidence=confidence,
        kind="text",
        reason="" if text and confidence >= min_confidence else f"low_confidence={confidence:.2f}",
    )


__all__ = ["is_available", "solve_text"]
