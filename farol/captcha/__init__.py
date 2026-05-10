"""CAPTCHA assist — best-effort, multi-backend, lightweight by default.

Two backends, used in order from cheapest to heaviest:

1. **Tesseract** (``farol[ocr]``) — classical CPU OCR for distorted-text
   CAPTCHAs. ~50-200 ms per image, $0, no GPU, no model download.
2. **Vision LLM** (``vision_llm`` on :class:`SearchEngine`) — handles
   image-grid challenges Tesseract can't read. Use ``ollama/qwen2.5vl:7b``
   for local, or any provider via LiteLLM.

What's **not** in scope:

- reCAPTCHA v3 (invisible scoring)
- Cloudflare Turnstile invisible
- Arkose / FunCaptcha 3D puzzles
- hCaptcha enterprise

For those, plug a commercial bypass via ``Site.behavior="external"``.
"""

from __future__ import annotations

from .solver import CaptchaResult, CaptchaSolver

__all__ = ["CaptchaResult", "CaptchaSolver"]
