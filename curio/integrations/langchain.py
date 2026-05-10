"""LangChain / LangGraph tool wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..engine import SearchEngine
from ._common import _DEFAULT_DESCRIPTION, build_engine, render_result

try:
    from langchain_core.tools import BaseTool  # type: ignore
except ImportError as e:
    raise ImportError(
        "LangChain integration requires langchain-core. pip install 'curio[langchain]'"
    ) from e

from pydantic import BaseModel, Field


class _Input(BaseModel):
    query: str = Field(..., description="Natural-language search query")
    depth: int = Field(1, ge=0, le=3)


class CurioSearchTool(BaseTool):
    name: str = "curio_search"
    description: str = _DEFAULT_DESCRIPTION
    args_schema: type = _Input
    engine: Any = None

    def __init__(
        self,
        catalog: str | Path | SearchEngine | None = None,
        **engine_kwargs,
    ):
        super().__init__()
        self.engine = build_engine(catalog, **engine_kwargs)

    @classmethod
    def from_yaml(cls, path: str | Path, **kwargs) -> CurioSearchTool:
        return cls(catalog=path, **kwargs)

    def _run(self, query: str, depth: int = 1) -> str:  # type: ignore[override]
        result = self.engine.search(query, depth=depth)
        return render_result(result)

    async def _arun(self, query: str, depth: int = 1) -> str:  # type: ignore[override]
        # Engine is sync; offload to a thread.
        import asyncio

        return await asyncio.to_thread(self._run, query, depth)


__all__ = ["CurioSearchTool"]
