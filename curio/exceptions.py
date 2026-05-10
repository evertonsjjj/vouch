"""Exception hierarchy for curio."""

from __future__ import annotations


class CurioError(Exception):
    """Base for all curio errors."""


class CatalogError(CurioError):
    """Catalog persistence or validation failed."""


class RouterError(CurioError):
    """Routing failed (LLM, embedding, or filter)."""


class AdapterError(CurioError):
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


class LLMError(CurioError):
    """Underlying LLM call failed after retries/fallbacks."""
