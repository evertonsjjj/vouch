"""End-to-end CAPTCHA solver test with synthetic images.

Generates 4 progressively-harder CAPTCHA images via Pillow, then runs each
through the full :class:`CaptchaSolver` chain (Tesseract → vision LLM).

Run:
    python examples/test_captcha_vision.py
"""

from __future__ import annotations

import os
import random
import sys
import time
from io import BytesIO

# Ensure unbuffered output on Windows
os.environ["PYTHONUNBUFFERED"] = "1"

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    print("ERROR: pillow not installed. Run: pip install Pillow")
    sys.exit(1)

from vouch._llm import LLMClient
from vouch.captcha import CaptchaSolver
from vouch.captcha.tesseract import is_available as tesseract_available

LOG = "./test-cache-captcha/run.log"
os.makedirs("./test-cache-captcha", exist_ok=True)
open(LOG, "w", encoding="utf-8").close()


def w(line: str = "") -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _font(size: int = 36) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Best-effort load a system font; fall back to PIL default."""
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/comic.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def make_captcha(text: str, *, difficulty: int = 1) -> bytes:
    """Render a CAPTCHA-like image with progressively more noise."""
    W, H = 320, 110
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    font = _font(48 if difficulty < 3 else 42)

    # Distort each character's position + rotation slightly.
    x = 18
    for ch in text:
        ch_img = Image.new("RGBA", (60, 80), (255, 255, 255, 0))
        ch_draw = ImageDraw.Draw(ch_img)
        color = (
            random.randint(0, 100),
            random.randint(0, 100),
            random.randint(0, 100),
        )
        ch_draw.text((6, 6), ch, font=font, fill=color)
        angle = random.uniform(-25, 25) if difficulty >= 2 else random.uniform(-10, 10)
        ch_img = ch_img.rotate(angle, expand=False, resample=Image.BILINEAR)
        img.paste(ch_img, (x, 15), ch_img)
        x += 38

    # Scribble lines (level 2+)
    if difficulty >= 2:
        for _ in range(3 + difficulty):
            x1, y1 = random.randint(0, W), random.randint(0, H)
            x2, y2 = random.randint(0, W), random.randint(0, H)
            draw.line([(x1, y1), (x2, y2)], fill=(0, 0, 0), width=1)

    # Speckle noise (level 3+)
    if difficulty >= 3:
        pixels = img.load()
        for _ in range(400 * difficulty):
            xn, yn = random.randint(0, W - 1), random.randint(0, H - 1)
            pixels[xn, yn] = (
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
            )

    # Slight blur softens the edges (typical CAPTCHA trick)
    if difficulty >= 2:
        img = img.filter(ImageFilter.GaussianBlur(radius=0.4))

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def main():
    w("=" * 70)
    w("CAPTCHA solver end-to-end smoke (Tesseract + qwen2.5vl:7b)")
    w("=" * 70)
    w(f"Tesseract available: {tesseract_available()}")

    # Build a vision LLM client
    w("\nWarming up qwen2.5vl:7b (first call loads ~6 GB into RAM)...")
    t0 = time.perf_counter()
    vision = LLMClient("ollama/qwen2.5vl:7b")
    # Cheap warm-up using a tiny blank image
    blank = Image.new("RGB", (40, 40), "white")
    buf = BytesIO()
    blank.save(buf, format="PNG")
    import base64

    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    try:
        _ = vision.vision("Just answer OK.", b64, max_tokens=10, timeout=300)
        w(f"  warm-up done in {time.perf_counter() - t0:.1f}s")
    except Exception as e:
        w(f"  warm-up FAILED: {type(e).__name__}: {e}")
        return

    # Build the solver — full chain
    solver = CaptchaSolver(vision_llm=vision, min_confidence=0.6, max_attempts=2)
    w(f"\nSolver config: prefer_tesseract=True, min_confidence=0.6")

    # 4 progressively-harder CAPTCHAs
    test_cases = [
        ("VOUCH2026", 1, "easy — minimal rotation, no noise"),
        ("AB7XQ9", 2, "medium — bigger rotation + scribble lines"),
        ("M4K9P2", 3, "hard — lines + speckle noise + blur"),
        ("XR8YT5", 4, "very hard — heavy speckle noise"),
    ]

    results = []
    for expected, diff, desc in test_cases:
        w("\n" + "-" * 70)
        w(f"Difficulty {diff}: {desc}")
        w(f"  expected: {expected}")
        img = make_captcha(expected, difficulty=diff)
        # Save the rendered image so we can eyeball it later.
        img_path = f"./test-cache-captcha/captcha_{diff}_{expected}.png"
        with open(img_path, "wb") as f:
            f.write(img)
        w(f"  image saved: {img_path}")

        t0 = time.perf_counter()
        r = solver.solve(img, kind="text")
        elapsed = time.perf_counter() - t0

        match_exact = (r.text or "").strip().upper() == expected.upper()
        match_loose = (r.text or "").strip().upper().replace("O", "0").replace("I", "1") == expected.upper().replace("O", "0").replace("I", "1")
        w(f"  result:   {r.text!r}")
        w(f"  solver:   {r.solver}")
        w(f"  conf:     {r.confidence:.2f}")
        w(f"  solved:   {r.solved}")
        w(f"  match:    exact={match_exact} loose={match_loose}")
        w(f"  time:     {elapsed:.1f}s")
        if r.reason:
            w(f"  reason:   {r.reason}")
        results.append((expected, r.text, r.solver, r.confidence, match_exact, elapsed))

    w("\n" + "=" * 70)
    w("SUMMARY")
    w("=" * 70)
    w(f"{'expected':<12}{'got':<12}{'solver':<14}{'conf':<8}{'match':<10}{'time':<8}")
    for expected, got, solver_name, conf, match, elapsed in results:
        w(
            f"{expected:<12}{(got or '-')[:10]:<12}{solver_name:<14}"
            f"{conf:<8.2f}{'YES' if match else 'no':<10}{elapsed:<8.1f}"
        )

    n_exact = sum(1 for _, _, _, _, m, _ in results if m)
    w(f"\nExact matches: {n_exact}/{len(results)}")
    w(f"Total tokens: {vision.tokens}")
    w(f"Total cost: ${vision.cost_usd:.4f} (Ollama → $0)")


if __name__ == "__main__":
    random.seed(42)  # reproducible CAPTCHAs
    main()
