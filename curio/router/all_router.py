"""Honest fallback — search every site every time. Good for ≤5 sites."""

from __future__ import annotations

from ..models import RouteDecision
from .base import Router, RoutingContext, filter_by_tags


class AllRouter(Router):
    def route(self, ctx: RoutingContext) -> list[RouteDecision]:
        sites = filter_by_tags(ctx.sites, ctx.only_tags, ctx.exclude_tags)
        return [RouteDecision(site=s.url, score=1.0, reason="all-strategy") for s in sites]
