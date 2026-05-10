"""Optional vision-LLM CAPTCHA assist.

Best-effort. Works on simple visual challenges (text OCR, image grid).
Does NOT defeat reCAPTCHA v3, Turnstile invisible, or Arkose 3D puzzles.
"""

from __future__ import annotations

from .solver import CaptchaResult, CaptchaSolver

__all__ = ["CaptchaResult", "CaptchaSolver"]
