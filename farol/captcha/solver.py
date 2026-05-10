"""CAPTCHA solver — Tesseract for text, vision LLM as upgrade for image grids.

Routing policy (in :meth:`CaptchaSolver.solve`):

* ``kind="text"``
    1. If ``prefer_tesseract`` and ``pytesseract`` + the system binary are
       available, try Tesseract first (CPU, <200 ms, $0).
    2. If Tesseract returns low confidence (or isn't available) **and** a
       ``vision_llm`` is configured, escalate to the LLM.
    3. Otherwise return the best result we got, marked unsolved.

* ``kind="image_grid"``
    Tesseract cannot handle grids. Use the vision LLM directly. If no
    LLM is configured, return ``unsupported``.

The solver gracefully degrades: an engine that has *neither* a vision_llm
*nor* Tesseract installed still works — it just always returns
``solved=False`` so the caller knows to treat the page as blocked.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any, ClassVar

log = logging.getLogger("farol.captcha")


@dataclass
class CaptchaResult:
    solved: bool
    text: str | None = None
    confidence: float = 0.0
    kind: str = "unknown"
    reason: str = ""
    solver: str = ""  # which engine produced this result ("tesseract", "vision_llm", ...)

    @classmethod
    def unsupported(cls, kind: str) -> CaptchaResult:
        return cls(solved=False, kind=kind, reason=f"{kind} is not supported")


_OCR_PROMPT = (
    "You are looking at a CAPTCHA image containing a short string of letters and digits. "
    "Read every character carefully, left to right. Preserve case exactly as shown. "
    "Do NOT add spaces, punctuation, quotes, or trailing characters that aren't visible. "
    "Reply with strict JSON only: "
    '{"text": "<exactly the characters>", "confidence": 0.0-1.0}'
)

_GRID_PROMPT = (
    "You are looking at a CAPTCHA image grid asking the user to select all squares "
    'containing: {target}. Reply with JSON {{"indices": [0,1,2,...], "confidence": 0.0-1.0}} '
    "where indices are 0-based, left-to-right, top-to-bottom."
)


class CaptchaSolver:
    """Multi-tier CAPTCHA solver — tries cheapest backend first.

    Parameters
    ----------
    vision_llm
        Optional :class:`farol._llm.LLMClient` configured with a vision model
        (``ollama/qwen2.5vl:7b``, ``anthropic/claude-haiku-4-5``, …).
        When ``None``, only Tesseract is used; image grids return ``unsupported``.
    min_confidence
        Threshold below which a result is marked unsolved. Triggers escalation
        to the next backend in the chain.
    max_attempts
        Per backend. Total worst-case attempts across the chain is
        ``2 * max_attempts`` (Tesseract + vision LLM).
    prefer_tesseract
        Default False — empirically, Tesseract fails on adversarial
        distortions (rotation + noise + scribble lines that real CAPTCHAs
        use). Set True only if you know your target CAPTCHAs are
        clean-text on a clean background (rare). When False *and* no
        ``vision_llm`` is set, Tesseract is still tried as a
        last-resort fallback — better than nothing.
    """

    SUPPORTED: ClassVar[set[str]] = {"text", "image_grid"}

    def __init__(
        self,
        vision_llm: Any | None = None,
        *,
        min_confidence: float = 0.7,
        max_attempts: int = 2,
        prefer_tesseract: bool = False,
    ):
        self.llm = vision_llm
        self.min_confidence = min_confidence
        self.max_attempts = max_attempts
        self.prefer_tesseract = prefer_tesseract

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def solve(
        self,
        image: bytes,
        *,
        kind: str = "text",
        target: str | None = None,
        mime: str = "image/png",
    ) -> CaptchaResult:
        if kind not in self.SUPPORTED:
            return CaptchaResult.unsupported(kind)

        if kind == "text":
            return self._solve_text(image, mime=mime)

        # image_grid — vision LLM required
        return self._solve_with_vision(image, kind="image_grid", target=target, mime=mime)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _solve_text(self, image: bytes, *, mime: str) -> CaptchaResult:
        """Routing:

        * ``prefer_tesseract=True``   — Tesseract first, vision LLM as fallback.
        * ``prefer_tesseract=False`` (default) — vision LLM first; if missing
          or if it fails, fall back to Tesseract as a last resort.
        """
        best = CaptchaResult(solved=False, kind="text")

        if self.prefer_tesseract:
            tess_result = self._try_tesseract(image)
            if tess_result is not None:
                if tess_result.solved:
                    return tess_result
                if tess_result.confidence > best.confidence:
                    best = tess_result
            if self.llm is not None:
                llm_result = self._solve_with_vision(image, kind="text", mime=mime)
                if llm_result.solved or llm_result.confidence > best.confidence:
                    return llm_result
            best.reason = best.reason or "no_backend_available"
            return best

        # Default path: vision LLM first, Tesseract as fallback.
        if self.llm is not None:
            llm_result = self._solve_with_vision(image, kind="text", mime=mime)
            if llm_result.solved:
                return llm_result
            if llm_result.confidence > best.confidence:
                best = llm_result

        tess_result = self._try_tesseract(image)
        if tess_result is not None:
            if tess_result.solved:
                return tess_result
            if tess_result.confidence > best.confidence:
                best = tess_result

        if best.solver == "":
            best.reason = best.reason or "no_backend_available"
        return best

    def _try_tesseract(self, image: bytes) -> CaptchaResult | None:
        """Return Tesseract's best guess, or ``None`` if it isn't installed."""
        try:
            from .tesseract import is_available, solve_text

            if not is_available():
                return None
            r = solve_text(image, min_confidence=self.min_confidence)
            r.solver = "tesseract"
            return r
        except Exception as e:
            log.warning("Tesseract backend errored: %s", e)
            return None

    def _solve_with_vision(
        self,
        image: bytes,
        *,
        kind: str,
        target: str | None = None,
        mime: str = "image/png",
    ) -> CaptchaResult:
        if self.llm is None:
            return CaptchaResult(
                solved=False,
                kind=kind,
                reason="vision_llm not configured (set vision_llm='ollama/qwen2.5vl:7b' on SearchEngine)",
            )

        b64 = base64.b64encode(image).decode("ascii")
        prompt = (
            _OCR_PROMPT
            if kind == "text"
            else _GRID_PROMPT.format(target=target or "the requested item")
        )
        last: CaptchaResult = CaptchaResult(solved=False, kind=kind, solver="vision_llm")
        for attempt in range(self.max_attempts):
            try:
                txt = self.llm.vision(prompt, b64, mime=mime, max_tokens=200)
                from .._llm import _parse_json_loose

                data = _parse_json_loose(txt)
            except Exception as e:
                log.warning("Vision-LLM captcha attempt %d failed: %s", attempt + 1, e)
                continue
            try:
                confidence = float(data.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            if kind == "text":
                text = data.get("text") or ""
                last = CaptchaResult(
                    solved=bool(text) and confidence >= self.min_confidence,
                    text=text,
                    confidence=confidence,
                    kind="text",
                    solver="vision_llm",
                )
            else:
                indices = data.get("indices") or []
                last = CaptchaResult(
                    solved=bool(indices) and confidence >= self.min_confidence,
                    text=",".join(str(i) for i in indices),
                    confidence=confidence,
                    kind="image_grid",
                    solver="vision_llm",
                )
            if last.solved:
                return last
        return last


__all__ = ["CaptchaResult", "CaptchaSolver"]


def solve_from_page(page: Any, solver: CaptchaSolver, *, locator: str = "img"):  # pragma: no cover
    """Grab the first CAPTCHA-looking image from a Playwright page and solve it."""
    img = page.locator(locator).first
    data = img.screenshot()
    return solver.solve(data, kind="text")
