"""Vision-LLM CAPTCHA solver — opt-in, best-effort."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any, ClassVar

from .._llm import LLMClient

log = logging.getLogger("farol.captcha")


@dataclass
class CaptchaResult:
    solved: bool
    text: str | None = None
    confidence: float = 0.0
    kind: str = "unknown"
    reason: str = ""

    @classmethod
    def unsupported(cls, kind: str) -> CaptchaResult:
        return cls(solved=False, kind=kind, reason=f"{kind} is not supported")


_OCR_PROMPT = (
    "You are looking at a CAPTCHA image. Read the text shown and reply with JSON "
    'of the form {"text": "...", "confidence": 0.0-1.0}. '
    "Do not add any other commentary."
)

_GRID_PROMPT = (
    "You are looking at a CAPTCHA image grid asking the user to select all squares "
    'containing: {target}. Reply with JSON {"indices": [0,1,2,...], "confidence": 0.0-1.0} '
    "where indices are 0-based, left-to-right, top-to-bottom."
)


class CaptchaSolver:
    SUPPORTED: ClassVar[set[str]] = {"text", "image_grid"}

    def __init__(
        self,
        vision_llm: LLMClient,
        *,
        min_confidence: float = 0.7,
        max_attempts: int = 2,
    ):
        self.llm = vision_llm
        self.min_confidence = min_confidence
        self.max_attempts = max_attempts

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
        b64 = base64.b64encode(image).decode("ascii")
        prompt = (
            _OCR_PROMPT
            if kind == "text"
            else _GRID_PROMPT.format(target=target or "the requested item")
        )
        last: CaptchaResult = CaptchaResult(solved=False, kind=kind)
        for attempt in range(self.max_attempts):
            try:
                txt = self.llm.vision(prompt, b64, mime=mime, max_tokens=200)
                from .._llm import _parse_json_loose

                data = _parse_json_loose(txt)
            except Exception as e:
                log.warning("Captcha attempt %d failed: %s", attempt + 1, e)
                continue
            confidence = float(data.get("confidence", 0.0))
            if kind == "text":
                text = data.get("text") or ""
                last = CaptchaResult(
                    solved=bool(text) and confidence >= self.min_confidence,
                    text=text,
                    confidence=confidence,
                    kind="text",
                )
            else:
                indices = data.get("indices") or []
                last = CaptchaResult(
                    solved=bool(indices) and confidence >= self.min_confidence,
                    text=",".join(str(i) for i in indices),
                    confidence=confidence,
                    kind="image_grid",
                )
            if last.solved:
                return last
        return last


__all__ = ["CaptchaResult", "CaptchaSolver"]


def solve_from_page(page: Any, solver: CaptchaSolver, *, locator: str = "img"):  # pragma: no cover
    """Convenience: grab the first CAPTCHA-looking image from a Playwright page and solve it."""
    img = page.locator(locator).first
    data = img.screenshot()
    return solver.solve(data, kind="text")
