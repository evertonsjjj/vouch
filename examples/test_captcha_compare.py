"""Re-run the CAPTCHA test with the tightened prompt + side-by-side Tesseract baseline.

Uses the *same* 4 images saved by ``test_captcha_vision.py`` so we get an
apples-to-apples comparison between Tesseract alone and qwen2.5vl:7b alone.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ["PYTHONUNBUFFERED"] = "1"

from vouch._llm import LLMClient
from vouch.captcha import CaptchaSolver
from vouch.captcha.tesseract import is_available as tesseract_available
from vouch.captcha.tesseract import solve_text as tesseract_solve

CACHE_DIR = Path("./test-cache-captcha")
LOG = CACHE_DIR / "compare.log"
LOG.write_text("", encoding="utf-8")


def w(line: str = "") -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


CASES = [
    ("VOUCH2026", CACHE_DIR / "captcha_1_VOUCH2026.png"),
    ("AB7XQ9", CACHE_DIR / "captcha_2_AB7XQ9.png"),
    ("M4K9P2", CACHE_DIR / "captcha_3_M4K9P2.png"),
    ("XR8YT5", CACHE_DIR / "captcha_4_XR8YT5.png"),
]


def _norm(s: str) -> str:
    """Trim trailing punctuation/space; uppercase for case-insensitive compare."""
    return (s or "").strip().rstrip(".+,;:-_!?\"'`).]}").upper()


def main():
    if not all(p.exists() for _, p in CASES):
        w("Missing CAPTCHA images. Run test_captcha_vision.py first.")
        return

    w("=" * 78)
    w("CAPTCHA backend comparison — same 4 images, both engines side by side")
    w("=" * 78)
    w(f"Tesseract available: {tesseract_available()}")

    # ---- Tesseract baseline ---------------------------------------------
    w("\n--- Tesseract only (psm=8, whitelist=alphanumeric, lang=eng+por+spa) ---")
    tess_results = []
    for expected, path in CASES:
        img = path.read_bytes()
        t0 = time.perf_counter()
        r = tesseract_solve(
            img,
            min_confidence=0.0,  # always return what we got
            whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
        )
        elapsed = time.perf_counter() - t0
        got = r.text or ""
        match = _norm(got) == _norm(expected)
        tess_results.append((expected, got, r.confidence, match, elapsed))
        w(f"  {expected:<12} -> {got!r:<18} conf={r.confidence:.2f}  match={'YES' if match else 'no':<3}  {elapsed:.2f}s")

    # ---- qwen2.5vl:7b alone with new prompt ----------------------------
    w("\n--- qwen2.5vl:7b only (new tightened prompt) ---")
    vision = LLMClient("ollama/qwen2.5vl:7b")
    solver = CaptchaSolver(vision_llm=vision, min_confidence=0.5, prefer_tesseract=False)

    vlm_results = []
    for expected, path in CASES:
        img = path.read_bytes()
        t0 = time.perf_counter()
        r = solver.solve(img, kind="text")
        elapsed = time.perf_counter() - t0
        got = r.text or ""
        match = _norm(got) == _norm(expected)
        vlm_results.append((expected, got, r.confidence, match, elapsed))
        w(f"  {expected:<12} -> {got!r:<18} conf={r.confidence:.2f}  match={'YES' if match else 'no':<3}  {elapsed:.2f}s")

    # ---- Side by side ----------------------------------------------------
    w("\n" + "=" * 78)
    w("SIDE BY SIDE")
    w("=" * 78)
    w(f"{'expected':<12}{'tesseract':<22}{'qwen2.5vl:7b':<22}{'match'}")
    w("-" * 70)
    n_tess = n_vlm = 0
    for (exp, tg, tc, tm, _tt), (_, vg, vc, vm, _vt) in zip(tess_results, vlm_results):
        tess_str = f"{tg!r}({tc:.2f}) {'✓' if tm else '✗'}"
        vlm_str = f"{vg!r}({vc:.2f}) {'✓' if vm else '✗'}"
        w(f"{exp:<12}{tess_str:<22}{vlm_str:<22}")
        if tm:
            n_tess += 1
        if vm:
            n_vlm += 1

    w(f"\nTesseract:    {n_tess}/4 exact (case-insensitive, trailing-punct stripped)")
    w(f"qwen2.5vl:7b: {n_vlm}/4 exact")
    w(f"\nTokens: {vision.tokens}  cost: ${vision.cost_usd:.4f}")


if __name__ == "__main__":
    main()
