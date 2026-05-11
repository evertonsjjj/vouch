"""Exception hierarchy for vouch."""

from __future__ import annotations


class VouchError(Exception):
    """Base for all vouch errors."""


# Back-compat alias for v0.1 users who imported ``CurioError``. Will be
# removed in v1.0.
CurioError = VouchError


class CatalogError(VouchError):
    """Catalog persistence or validation failed."""


class RouterError(VouchError):
    """Routing failed (LLM, embedding, or filter)."""


class AdapterError(VouchError):
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


class LLMError(VouchError):
    """Underlying LLM call failed after retries/fallbacks."""
