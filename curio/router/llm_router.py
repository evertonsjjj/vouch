"""LLM-based router — single completion picks the top-K most relevant sites."""

from __future__ import annotations

import logging
from typing import Any

from .._llm import LLMClient
from ..exceptions import RouterError
from ..models import RouteDecision
from .base import Router, RoutingContext, filter_by_tags

log = logging.getLogger("curio.router.llm")

_SYSTEM = """You are a search router. Given a user query and a catalog of trusted sources, \
pick the sources most likely to contain a useful answer. Be aggressive about filtering — \
do not include sources that are obviously off-topic. Output strict JSON only."""

_USER_TMPL = """Query: {query}

Sources (one per line, format: url || category || description || tags):
{catalog}

Return JSON of the form:
{{
  "picks": [
    {{"site": "<url>", "score": 0.0-1.0, "reason": "<short justification>"}},
    ...
  ]
}}

Pick at most {top_k} sources. Order by relevance (most relevant first). \
If none of the sources fit, return an empty list."""


class LLMRouter(Router):
    def __init__(
        self,
        llm: str | list[str] | LLMClient = "ollama/qwen2.5:14b",
        *,
        api_keys: dict[str, str] | None = None,
    ):
        self.llm = llm if isinstance(llm, LLMClient) else LLMClient(llm, api_keys=api_keys)

    def route(self, ctx: RoutingContext) -> list[RouteDecision]:
        sites = filter_by_tags(ctx.sites, ctx.only_tags, ctx.exclude_tags)
        if not sites:
            return []
        if len(sites) <= ctx.top_k:
            return [RouteDecision(site=s.url, score=1.0, reason="under-top-k") for s in sites]

        catalog_lines = []
        for s in sites:
            tags = ",".join(s.tags) if s.tags else ""
            catalog_lines.append(
                f"{s.url} || {s.category or ''} || {s.description or ''} || {tags}"
            )

        prompt = _USER_TMPL.format(
            query=ctx.query,
            catalog="\n".join(catalog_lines),
            top_k=ctx.top_k,
        )
        try:
            data = self.llm.chat_json(
                [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=600,
            )
        except Exception as e:
            log.warning("LLM router fell back to all-sites: %s", e)
            return [
                RouteDecision(site=s.url, score=0.5, reason="llm-error") for s in sites[: ctx.top_k]
            ]

        return _coerce_decisions(data, sites, ctx.top_k)


def _coerce_decisions(data: Any, sites, top_k: int) -> list[RouteDecision]:
    valid_urls = {s.url for s in sites}
    raw = []
    if isinstance(data, dict):
        raw = data.get("picks") or data.get("sites") or data.get("results") or []
    elif isinstance(data, list):
        raw = data
    decisions: list[RouteDecision] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = (item.get("site") or item.get("url") or "").strip().lower()
        if url.startswith("http"):
            from ..catalog import _normalize_domain

            url = _normalize_domain(url)
        if url not in valid_urls:
            continue
        try:
            score = float(item.get("score", 0.5))
        except (TypeError, ValueError):
            score = 0.5
        decisions.append(
            RouteDecision(
                site=url, score=max(0.0, min(1.0, score)), reason=str(item.get("reason", ""))
            )
        )
    if not decisions:
        raise RouterError("LLM router returned no usable picks")
    decisions.sort(key=lambda d: d.score, reverse=True)
    return decisions[:top_k]
