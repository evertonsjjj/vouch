"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from curio import Catalog, SearchEngine, Site


@pytest.fixture
def empty_catalog(tmp_path) -> Catalog:
    return Catalog(tmp_path / "catalog.db")


@pytest.fixture
def sample_sites() -> list[Site]:
    return [
        Site(url="cvm.gov.br", category="regulação financeira BR", tags=["gov", "financeiro"]),
        Site(url="arxiv.org", category="papers acadêmicos", tags=["research", "ml", "ai"]),
        Site(url="news.ycombinator.com", category="notícias tech", tags=["tech", "discussion"]),
        Site(url="github.com", category="código", tags=["dev", "code"]),
        Site(url="stackoverflow.com", category="QA dev", tags=["dev", "qa"]),
    ]


@pytest.fixture
def populated_catalog(empty_catalog, sample_sites) -> Catalog:
    for s in sample_sites:
        empty_catalog.add(s, replace=True)
    return empty_catalog


@pytest.fixture
def fake_engine(tmp_path, populated_catalog) -> SearchEngine:
    return SearchEngine(
        llm="openai/gpt-4o-mini",
        cache_dir=str(tmp_path / "cache"),
        catalog=populated_catalog,
        router_strategy="all",
    )
