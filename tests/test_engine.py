"""Engine wiring — uses a mocked adapter so we don't hit the network."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from curio import Chunk, SearchEngine
from curio.adapters.base import AdapterContext, SiteAdapter


class _StubAdapter(SiteAdapter):
    def __init__(self, *args, **kwargs):
        pass

    def search(self, ctx: AdapterContext) -> list[Chunk]:
        return [
            Chunk(
                source_url=f"https://{ctx.site.url}/result/{i}",
                site=ctx.site.url,
                title=f"{ctx.site.url} result {i} for {ctx.query}",
                snippet="lorem ipsum dolor sit amet",
                relevance_score=0.5 + i * 0.1,
            )
            for i in range(3)
        ]

    def close(self) -> None:
        pass


@pytest.fixture
def stub_engine(tmp_path, populated_catalog) -> SearchEngine:
    return SearchEngine(
        llm="openai/gpt-4o-mini",
        cache_dir=str(tmp_path / "cache"),
        catalog=populated_catalog,
        router_strategy="all",
        parallel_sites=2,
        auto_escalate_adapter=False,  # tests rely on patching build_adapter directly
    )


def test_search_uses_stub(stub_engine):
    with patch("curio.engine.build_adapter", lambda *a, **kw: _StubAdapter()):
        result = stub_engine.search("example query", depth=1, max_results=10)
    assert len(result.chunks) > 0
    assert result.status in ("ok", "partial")
    assert result.duration_ms > 0


def test_router_decisions_present(stub_engine):
    with patch("curio.engine.build_adapter", lambda *a, **kw: _StubAdapter()):
        result = stub_engine.search("test", depth=0, max_results=5)
    assert len(result.routing_decisions) > 0


def test_search_with_explicit_sites(stub_engine):
    with patch("curio.engine.build_adapter", lambda *a, **kw: _StubAdapter()):
        result = stub_engine.search("query", sites=["arxiv.org"], depth=1)
    assert all("arxiv.org" in c.site for c in result.chunks)


def test_failure_in_one_site_does_not_fail_all(stub_engine):
    class _SometimesFail(_StubAdapter):
        def search(self, ctx):
            if "arxiv.org" in ctx.site.url:
                raise RuntimeError("simulated")
            return super().search(ctx)

    with patch("curio.engine.build_adapter", lambda *a, **kw: _SometimesFail()):
        result = stub_engine.search("test", depth=1)
    assert any("arxiv.org" in e for e in result.errors)
    assert result.chunks  # other sites still produced results
