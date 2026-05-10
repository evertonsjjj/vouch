"""CrewAI tool wrapper around curio's SearchEngine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..engine import SearchEngine
from ._common import _DEFAULT_DESCRIPTION, build_engine, render_result

try:
    from crewai.tools import BaseTool  # type: ignore
except ImportError:
    try:
        from crewai_tools import BaseTool  # type: ignore
    except ImportError as e:
        raise ImportError(
            "CrewAI integration requires crewai. pip install 'curio[crewai]'"
        ) from e

from pydantic import BaseModel, Field


class _Input(BaseModel):
    query: str = Field(..., description="Natural-language search query")
    depth: int = Field(1, ge=0, le=3, description="Cost/quality knob: 0–3")


class CurioSearchTool(BaseTool):
    """Drop-in CrewAI tool: ``tools=[CurioSearchTool(catalog="sites.yaml")]``."""

    name: str = "curio_search"
    description: str = _DEFAULT_DESCRIPTION
    args_schema: type = _Input
    engine: Any = None
    default_depth: int = 1

    def __init__(
        self,
        catalog: str | Path | SearchEngine | None = None,
        *,
        default_depth: int = 1,
        **engine_kwargs,
    ):
        super().__init__()
        self.engine = build_engine(catalog, **engine_kwargs)
        self.default_depth = default_depth

    def _run(self, query: str, depth: int | None = None) -> str:  # type: ignore[override]
        result = self.engine.search(query, depth=depth or self.default_depth)
        return render_result(result)


__all__ = ["CurioSearchTool"]
