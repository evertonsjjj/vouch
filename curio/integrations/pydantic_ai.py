"""PydanticAI tool factory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..engine import SearchEngine
from ..models import SearchResult
from ._common import build_engine

try:
    from pydantic_ai import Tool  # type: ignore
except ImportError as e:
    raise ImportError(
        "PydanticAI integration requires pydantic-ai. pip install 'curio[pydantic-ai]'"
    ) from e


def curio_tool(
    catalog: str | Path | SearchEngine | None = None,
    *,
    default_depth: int = 1,
    **engine_kwargs,
) -> "Tool":
    """Build a PydanticAI ``Tool`` that wraps a curio SearchEngine.

    Usage::

        from pydantic_ai import Agent
        from curio.integrations.pydantic_ai import curio_tool

        agent = Agent("anthropic:claude-sonnet-4-6", tools=[curio_tool("sites.yaml")])
    """
    engine: SearchEngine = build_engine(catalog, **engine_kwargs)

    async def _curio_search(query: str, depth: int = default_depth) -> SearchResult:
        """Search a curated list of trusted sources."""
        import asyncio

        return await asyncio.to_thread(engine.search, query, depth=depth)

    return Tool(_curio_search, name="curio_search", description="Curated multi-site search")


__all__ = ["curio_tool"]
