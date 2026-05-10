"""Router strategies — focused on logic, not LLM behavior."""

from __future__ import annotations

from farol.router import AllRouter, TagRouter, build_router
from farol.router.base import RoutingContext


def test_all_router_returns_everything(sample_sites):
    r = AllRouter()
    out = r.route(RoutingContext(query="anything", sites=sample_sites, top_k=2))
    assert {d.site for d in out} == {s.url for s in sample_sites}


def test_tag_router_scores_overlap(sample_sites):
    r = TagRouter()
    decisions = r.route(RoutingContext(query="dev workflow tips", sites=sample_sites, top_k=2))
    sites = [d.site for d in decisions]
    assert "github.com" in sites or "stackoverflow.com" in sites


def test_tag_router_falls_back_when_no_overlap(sample_sites):
    r = TagRouter(fall_back_to_all=True)
    decisions = r.route(
        RoutingContext(query="completely unrelated query", sites=sample_sites, top_k=2)
    )
    assert len(decisions) > 0


def test_factory_unknown_strategy_raises():
    import pytest

    with pytest.raises(ValueError):
        build_router("magic")
