"""Tag-based router — exact-match on Site.tags. No LLM, no embedding."""

from __future__ import annotations

import re

from ..models import RouteDecision
from .base import Router, RoutingContext, filter_by_tags

_TOKEN = re.compile(r"\w+", re.UNICODE)


class TagRouter(Router):
    """Score sites by how many of their tags appear in the query.

    Useful when callers tag sites with explicit query domains (``regulação``,
    ``ml``, ``finance``) and queries naturally include those terms.
    """

    def __init__(self, *, fall_back_to_all: bool = True):
        self.fall_back_to_all = fall_back_to_all

    def route(self, ctx: RoutingContext) -> list[RouteDecision]:
        sites = filter_by_tags(ctx.sites, ctx.only_tags, ctx.exclude_tags)
        tokens = {t.lower() for t in _TOKEN.findall(ctx.query)}
        scored = []
        for s in sites:
            tag_set = {t.lower() for t in s.tags}
            if not tag_set:
                continue
            overlap = tokens & tag_set
            if not overlap:
                continue
            score = len(overlap) / max(len(tag_set), 1)
            scored.append(
                RouteDecision(
                    site=s.url,
                    score=round(score, 3),
                    reason=f"tag-match: {','.join(sorted(overlap))}",
                )
            )
        scored.sort(key=lambda d: d.score, reverse=True)
        if not scored and self.fall_back_to_all:
            return [RouteDecision(site=s.url, score=0.5, reason="tag-fallback") for s in sites[: ctx.top_k]]
        return scored[: ctx.top_k]
