"""SiteAdapter Protocol — the contract for per-site search execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..catalog import Site
from ..models import Chunk


@dataclass
class AdapterContext:
    site: Site
    query: str
    depth: int
    max_results: int = 10
    timeout: float = 60.0
    extra: dict = field(default_factory=dict)


@runtime_checkable
class SiteAdapter(Protocol):
    """Contract for any per-site search executor."""

    def search(self, ctx: AdapterContext) -> list[Chunk]: ...

    def close(self) -> None: ...
