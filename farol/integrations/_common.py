"""Shared helpers for framework integrations."""

from __future__ import annotations

from pathlib import Path

from ..engine import SearchEngine


def build_engine(catalog: str | Path | SearchEngine | None, **kwargs) -> SearchEngine:
    if isinstance(catalog, SearchEngine):
        return catalog
    if catalog and str(catalog).endswith((".yaml", ".yml")):
        return SearchEngine.from_yaml(catalog, **kwargs)
    return SearchEngine(**kwargs)


_DEFAULT_DESCRIPTION = (
    "Search a curated list of trusted sources using farol. "
    "Provide a natural-language query; you'll get back a list of result chunks "
    "(title, URL, snippet, score). Use depth=0 for homepage skim, "
    "depth=1 for search results, depth=2 for full-content extraction."
)


def render_result(result, *, max_chars_per_chunk: int = 400) -> str:
    return result.to_text(max_chars_per_chunk=max_chars_per_chunk)


__all__ = ["build_engine", "render_result"]
