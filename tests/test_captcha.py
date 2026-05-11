"""CaptchaSolver routing — Tesseract → vision LLM chain.

We don't depend on a real Tesseract binary or a real vision model. The two
backends are stubbed at the module-import level via monkeypatch so the tests
run on any machine, including CI.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from vouch.captcha import CaptchaResult, CaptchaSolver


class _FakeVisionLLM:
    """Mimics LLMClient.vision — returns a fixed JSON string."""

    def __init__(self, payload: str):
        self.payload = payload
        self.calls = 0

    def vision(self, prompt, b64, *, mime="image/png", **kwargs):
        self.calls += 1
        return self.payload


# ----------------------------------------------------------------------
# Tesseract path
# ----------------------------------------------------------------------


def test_text_uses_tesseract_first_when_preferred():
    """Opt-in: prefer_tesseract=True → Tesseract resolves before the LLM is touched."""
    fake_llm = _FakeVisionLLM('{"text":"WRONG","confidence":0.99}')
    solver = CaptchaSolver(vision_llm=fake_llm, min_confidence=0.5, prefer_tesseract=True)

    with (
        patch("vouch.captcha.tesseract.is_available", return_value=True),
        patch(
            "vouch.captcha.tesseract.solve_text",
            return_value=CaptchaResult(
                solved=True, text="ABC123", confidence=0.85, kind="text", solver="tesseract"
            ),
        ),
    ):
        result = solver.solve(b"<image-bytes>", kind="text")

    assert result.solved
    assert result.text == "ABC123"
    assert result.solver == "tesseract"
    assert fake_llm.calls == 0


def test_default_uses_vision_llm_first():
    """Default (prefer_tesseract=False): vision LLM goes first; Tesseract not called when LLM solves."""
    fake_llm = _FakeVisionLLM('{"text":"FROM_LLM","confidence":0.95}')
    solver = CaptchaSolver(
        vision_llm=fake_llm, min_confidence=0.5
    )  # prefer_tesseract default = False

    with (
        patch("vouch.captcha.tesseract.is_available", return_value=True) as ta,
        patch("vouch.captcha.tesseract.solve_text") as ts,
    ):
        result = solver.solve(b"<image-bytes>", kind="text")

    assert result.solved
    assert result.text == "FROM_LLM"
    assert result.solver == "vision_llm"
    # Tesseract should not have been queried at all when LLM solves
    assert ta.call_count == 0
    ts.assert_not_called()


def test_text_escalates_to_llm_when_tesseract_unconfident():
    """prefer_tesseract=True: Tesseract returns low confidence → vision LLM picks up."""
    fake_llm = _FakeVisionLLM('{"text":"BETTER","confidence":0.92}')
    solver = CaptchaSolver(vision_llm=fake_llm, min_confidence=0.7, prefer_tesseract=True)

    with (
        patch("vouch.captcha.tesseract.is_available", return_value=True),
        patch(
            "vouch.captcha.tesseract.solve_text",
            return_value=CaptchaResult(
                solved=False, text="garbled", confidence=0.30, kind="text", solver="tesseract"
            ),
        ),
    ):
        result = solver.solve(b"<image-bytes>", kind="text")

    assert result.solved
    assert result.text == "BETTER"
    assert result.solver == "vision_llm"
    assert fake_llm.calls == 1


def test_default_falls_back_to_tesseract_when_llm_fails():
    """Default chain: vision LLM returns low conf → Tesseract used as fallback."""
    fake_llm = _FakeVisionLLM('{"text":"weak","confidence":0.20}')
    solver = CaptchaSolver(
        vision_llm=fake_llm, min_confidence=0.7
    )  # default prefer_tesseract=False

    with (
        patch("vouch.captcha.tesseract.is_available", return_value=True),
        patch(
            "vouch.captcha.tesseract.solve_text",
            return_value=CaptchaResult(
                solved=True, text="GOOD", confidence=0.85, kind="text", solver="tesseract"
            ),
        ),
    ):
        result = solver.solve(b"<image-bytes>", kind="text")

    assert result.solved
    assert result.text == "GOOD"
    assert result.solver == "tesseract"


def test_text_returns_best_when_no_llm_and_tesseract_weak():
    """No LLM + weak Tesseract → return Tesseract's result, marked unsolved."""
    solver = CaptchaSolver(vision_llm=None, min_confidence=0.7)

    with (
        patch("vouch.captcha.tesseract.is_available", return_value=True),
        patch(
            "vouch.captcha.tesseract.solve_text",
            return_value=CaptchaResult(
                solved=False, text="weak", confidence=0.30, kind="text", solver="tesseract"
            ),
        ),
    ):
        result = solver.solve(b"<image-bytes>", kind="text")

    assert not result.solved
    assert result.text == "weak"
    assert result.solver == "tesseract"


def test_text_skips_tesseract_when_unavailable():
    """No Tesseract + no LLM → graceful no_backend_available."""
    solver = CaptchaSolver(vision_llm=None)
    with patch("vouch.captcha.tesseract.is_available", return_value=False):
        result = solver.solve(b"<image-bytes>", kind="text")
    assert not result.solved
    assert result.solver == "" or "no_backend" in result.reason or "vision_llm" in result.reason


def test_prefer_tesseract_false_skips_to_llm():
    """``prefer_tesseract=False`` (default): when the LLM solves, Tesseract is not queried."""
    fake_llm = _FakeVisionLLM('{"text":"DIRECT","confidence":0.95}')
    solver = CaptchaSolver(vision_llm=fake_llm, prefer_tesseract=False, min_confidence=0.5)

    with patch("vouch.captcha.tesseract.is_available", return_value=True) as is_avail:
        result = solver.solve(b"<image-bytes>", kind="text")

    assert result.solved
    assert result.solver == "vision_llm"
    # Tesseract availability check should never run when the LLM already solved.
    assert is_avail.call_count == 0


# ----------------------------------------------------------------------
# Image-grid path
# ----------------------------------------------------------------------


def test_image_grid_requires_vision_llm():
    solver = CaptchaSolver(vision_llm=None)
    result = solver.solve(b"<image>", kind="image_grid", target="traffic lights")
    assert not result.solved
    assert "vision_llm" in result.reason


def test_image_grid_uses_vision_llm():
    fake_llm = _FakeVisionLLM('{"indices":[0,2,4],"confidence":0.81}')
    solver = CaptchaSolver(vision_llm=fake_llm, min_confidence=0.7)
    result = solver.solve(b"<image>", kind="image_grid", target="cars")
    assert result.solved
    assert result.text == "0,2,4"
    assert result.solver == "vision_llm"
    assert fake_llm.calls == 1


def test_image_grid_does_not_call_tesseract():
    fake_llm = _FakeVisionLLM('{"indices":[1],"confidence":0.9}')
    solver = CaptchaSolver(vision_llm=fake_llm)
    with patch("vouch.captcha.tesseract.solve_text") as solve_text:
        solver.solve(b"<image>", kind="image_grid", target="cars")
    solve_text.assert_not_called()


# ----------------------------------------------------------------------
# Unsupported kinds
# ----------------------------------------------------------------------


def test_unsupported_kind_returns_unsupported():
    solver = CaptchaSolver(vision_llm=None)
    result = solver.solve(b"x", kind="recaptcha_v3")
    assert not result.solved
    assert "not supported" in result.reason


# ----------------------------------------------------------------------
# Tesseract module level (offline — no real binary needed)
# ----------------------------------------------------------------------


def test_tesseract_is_available_false_when_pytesseract_missing():
    from vouch.captcha import tesseract

    with patch.dict("sys.modules", {"pytesseract": None}):
        assert tesseract.is_available() is False


def test_tesseract_solve_returns_unsolved_when_deps_missing():
    from vouch.captcha import tesseract

    # Force the import inside solve_text to fail by removing pytesseract from sys.modules
    with patch.dict("sys.modules", {"pytesseract": None, "PIL": None}):
        result = tesseract.solve_text(b"<image>")
    assert not result.solved
    assert "deps missing" in result.reason or "OCR" in result.reason


@pytest.mark.skipif(
    not __import__("vouch.captcha.tesseract", fromlist=["is_available"]).is_available(),
    reason="Tesseract binary not installed on this machine",
)
def test_tesseract_smoke_with_real_binary(tmp_path):
    """If a real Tesseract binary is installed, verify the wrapper at least
    returns *something* on a blank-white image (the result will be empty
    string with low confidence; we don't assert content, only that we
    don't crash).
    """
    from PIL import Image  # type: ignore

    from vouch.captcha import tesseract

    img_path = tmp_path / "blank.png"
    Image.new("RGB", (200, 60), "white").save(img_path)
    result = tesseract.solve_text(img_path.read_bytes())
    # Blank image → text empty or very low confidence
    assert isinstance(result, CaptchaResult)
    assert result.kind == "text"
