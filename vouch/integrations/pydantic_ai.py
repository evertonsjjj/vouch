"""PydanticAI tool factory."""

from __future__ import annotations

from pathlib import Path

from ..engine import SearchEngine
from ..models import SearchResult
from ._common import build_engine

try:
    from pydantic_ai import Tool  # type: ignore
except ImportError as e:
    raise ImportError(
        "PydanticAI integration requires pydantic-ai. pip install 'vouch[pydantic-ai]'"
    ) from e


def vouch_tool(
    catalog: str | Path | SearchEngine | None = None,
    *,
    default_depth: int = 1,
    **engine_kwargs,
) -> Tool:
    """Build a PydanticAI ``Tool`` that wraps a vouch SearchEngine.

    Usage::

        from pydantic_ai import Agent
        from vouch.integrations.pydantic_ai import vouch_tool

        agent = Agent("anthropic:claude-sonnet-4-6", tools=[vouch_tool("sites.yaml")])
    """
    engine: SearchEngine = build_engine(catalog, **engine_kwargs)

    async def _vouch_search(query: str, depth: int = default_depth) -> SearchResult:
        """Search a curated list of trusted sources."""
        import asyncio

        return await asyncio.to_thread(engine.search, query, depth=depth)

    return Tool(_vouch_search, name="vouch_search", description="Curated multi-site search")


__all__ = ["vouch_tool"]
