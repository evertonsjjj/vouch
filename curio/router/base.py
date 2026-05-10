"""Router protocol and shared context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..catalog import Site
from ..models import RouteDecision


@dataclass
class RoutingContext:
    query: str
    sites: list[Site]
    top_k: int = 3
    only_tags: list[str] | None = None
    exclude_tags: list[str] | None = None
    explain: bool = False
    extra: dict = field(default_factory=dict)


@runtime_checkable
class Router(Protocol):
    """Decide which sites to search for a given query."""

    def route(self, ctx: RoutingContext) -> list[RouteDecision]: ...


def filter_by_tags(sites: list[Site], only: list[str] | None, exclude: list[str] | None) -> list[Site]:
    out = list(sites)
    if only:
        wanted = set(only)
        out = [s for s in out if wanted & set(s.tags)]
    if exclude:
        bad = set(exclude)
        out = [s for s in out if not (bad & set(s.tags))]
    return out
