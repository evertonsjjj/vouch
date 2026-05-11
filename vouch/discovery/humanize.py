"""Human-like behavior helpers — pauses, typing rhythm, light typo injection.

These reduce signals from naive behavioral analytics. They do **not** defeat
modern bot protection (Cloudflare Turnstile, DataDome). See README §Limits.
"""

from __future__ import annotations

import asyncio
import random
import string
from typing import Any

_SPEED_MS = {
    "fast": (30, 90),
    "natural": (60, 250),
    "slow": (120, 380),
}

_READ_PAUSE = (0.5, 3.0)


def lognormal_ms(low: int, high: int) -> float:
    """Sample a lognormal-ish delay clipped to [low, high]."""
    mu = (low + high) / 2
    sigma = (high - low) / 4
    val = random.gauss(mu, sigma)
    return max(low, min(high, val))


def reading_pause() -> float:
    return random.uniform(*_READ_PAUSE)


async def type_humanlike(
    locator: Any, text: str, *, speed: str = "natural", typo_rate: float = 0.02
) -> None:
    """Type *text* into a Playwright locator with human-ish rhythm and occasional typos."""
    low, high = _SPEED_MS.get(speed, _SPEED_MS["natural"])
    for ch in text:
        if random.random() < typo_rate and ch.isalpha():
            wrong = random.choice(string.ascii_lowercase)
            await locator.type(wrong, delay=lognormal_ms(low, high))
            await asyncio.sleep(lognormal_ms(60, 220) / 1000)
            await locator.press("Backspace")
        await locator.type(ch, delay=lognormal_ms(low, high))
    await asyncio.sleep(reading_pause() / 6)


def in_business_hours(now=None) -> bool:
    from datetime import datetime

    n = now or datetime.now()
    return 8 <= n.hour < 19 and n.weekday() < 5


__all__ = ["in_business_hours", "lognormal_ms", "reading_pause", "type_humanlike"]
