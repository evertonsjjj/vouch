"""Exception hierarchy for farol."""

from __future__ import annotations


class FarolError(Exception):
    """Base for all farol errors."""


# Back-compat alias for v0.1 users who imported ``CurioError``. Will be
# removed in v1.0.
CurioError = FarolError


class CatalogError(FarolError):
    """Catalog persistence or validation failed."""


class RouterError(FarolError):
    """Routing failed (LLM, embedding, or filter)."""


class AdapterError(FarolError):
    """Site adapter failed (network, parsing, browser)."""


class DiscoveryError(AdapterError):
    """Search-bar discovery failed for a site."""


class BlockedError(AdapterError):
    """Site actively blocked the request (CAPTCHA, WAF, rate limit)."""

    def __init__(self, message: str, *, reason: str = "unknown", suggestion: str | None = None):
        super().__init__(message)
        self.reason = reason
        self.suggestion = suggestion


class ExtractionError(AdapterError):
    """Content extraction failed."""


class LLMError(FarolError):
    """Underlying LLM call failed after retries/fallbacks."""
