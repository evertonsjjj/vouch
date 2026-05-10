"""Embedding-based router — cosine similarity between query and Site descriptions.

Lazy-loads sentence-transformers; if it's not installed we surface a clear error.
The catalog embeddings are cached by Site URL + text hash.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from ..catalog import Site
from ..exceptions import RouterError
from ..models import RouteDecision
from .base import Router, RoutingContext, filter_by_tags

log = logging.getLogger("curio.router.embedding")


class EmbeddingRouter(Router):
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        *,
        threshold: float = 0.15,
    ):
        self.model_name = model_name
        self.threshold = threshold
        self._model: Any = None
        self._cache: dict[str, "Any"] = {}  # url -> embedding

    def _ensure_model(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as e:
            raise RouterError(
                "EmbeddingRouter requires sentence-transformers. "
                "Install with: pip install 'curio[embedding]'"
            ) from e
        self._model = SentenceTransformer(self.model_name)

    def _key(self, site: Site) -> str:
        h = hashlib.sha256(site.routing_blob().encode("utf-8")).hexdigest()[:16]
        return f"{site.url}:{h}"

    def _embed_site(self, site: Site):
        key = self._key(site)
        if key in self._cache:
            return self._cache[key]
        emb = self._model.encode(site.routing_blob(), normalize_embeddings=True)
        self._cache[key] = emb
        return emb

    def route(self, ctx: RoutingContext) -> list[RouteDecision]:
        sites = filter_by_tags(ctx.sites, ctx.only_tags, ctx.exclude_tags)
        if not sites:
            return []
        try:
            self._ensure_model()
        except RouterError as e:
            log.warning("%s — falling back to all sites", e)
            return [RouteDecision(site=s.url, score=0.5, reason="no-embed-model") for s in sites[: ctx.top_k]]

        import numpy as np  # type: ignore

        query_emb = self._model.encode(ctx.query, normalize_embeddings=True)
        scored: list[RouteDecision] = []
        for s in sites:
            site_emb = self._embed_site(s)
            score = float(np.dot(query_emb, site_emb))
            if score >= self.threshold:
                scored.append(
                    RouteDecision(
                        site=s.url,
                        score=round(score, 3),
                        reason=f"cosine={score:.3f}",
                    )
                )
        if not scored:
            return [
                RouteDecision(site=s.url, score=0.0, reason="below-threshold")
                for s in sites[: ctx.top_k]
            ]
        scored.sort(key=lambda d: d.score, reverse=True)
        return scored[: ctx.top_k]
