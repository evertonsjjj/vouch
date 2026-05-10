"""Routing strategies — pick the most relevant Sites for a query."""

from __future__ import annotations

from .all_router import AllRouter
from .base import Router, RoutingContext
from .embedding_router import EmbeddingRouter
from .llm_router import LLMRouter
from .tag_router import TagRouter

__all__ = [
    "AllRouter",
    "EmbeddingRouter",
    "LLMRouter",
    "Router",
    "RoutingContext",
    "TagRouter",
    "build_router",
]


def build_router(strategy: str, **kwargs) -> Router:
    """Factory used by SearchEngine to pick a strategy from config."""
    strategy = strategy.lower()
    if strategy == "llm":
        return LLMRouter(**kwargs)
    if strategy == "embedding":
        return EmbeddingRouter(**kwargs)
    if strategy == "tags":
        return TagRouter(**kwargs)
    if strategy == "all":
        return AllRouter()
    raise ValueError(f"Unknown router strategy: {strategy!r}")
