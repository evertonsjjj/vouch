"""Result and routing data models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Chunk(BaseModel):
    """One unit of search output — a page, post, or document."""

    source_url: str
    site: str
    site_category: str | None = None
    title: str
    snippet: str = ""
    content: str | None = None
    relevance_score: float = 0.0
    extracted_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")

    def __str__(self) -> str:
        head = f"[{self.site}] {self.title}".strip()
        return f"{head}\n{self.snippet}".strip()


class RouteDecision(BaseModel):
    site: str
    score: float
    reason: str = ""

    model_config = ConfigDict(extra="ignore")


class TokenUsage(BaseModel):
    input: int = 0
    output: int = 0

    def add(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(input=self.input + other.input, output=self.output + other.output)


class CacheStats(BaseModel):
    hits: int = 0
    misses: int = 0


class SearchResult(BaseModel):
    """Bundle returned by SearchEngine.search()."""

    query: str
    chunks: list[Chunk] = Field(default_factory=list)
    sites_searched: list[str] = Field(default_factory=list)
    routing_decisions: list[RouteDecision] = Field(default_factory=list)
    duration_ms: float = 0.0
    cost_estimate_usd: float = 0.0
    tokens_used: TokenUsage = Field(default_factory=TokenUsage)
    cache_stats: CacheStats = Field(default_factory=CacheStats)
    status: str = "ok"  # "ok" | "blocked" | "partial" | "low_quality"
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    quality_warning: str | None = None

    model_config = ConfigDict(extra="ignore")

    def __iter__(self):
        return iter(self.chunks)

    def __len__(self):
        return len(self.chunks)

    def __getitem__(self, i):
        return self.chunks[i]

    def to_text(self, max_chars_per_chunk: int = 400) -> str:
        """Compact rendering — useful as an LLM tool result."""
        lines = [f"# Results for: {self.query}", ""]
        if self.quality_warning:
            lines.append(f"_(warning: {self.quality_warning})_")
            lines.append("")
        for c in self.chunks:
            body = (c.content or c.snippet)[:max_chars_per_chunk]
            lines.append(f"## [{c.site}] {c.title}")
            lines.append(c.source_url)
            lines.append(body)
            lines.append("")
        return "\n".join(lines)

    def to_markdown(self, *, include_meta: bool = True) -> str:
        """Markdown-formatted, suitable for chat / docs / LLM context."""
        out: list[str] = [f"# Search results for: *{self.query}*", ""]
        if include_meta:
            out.append(
                f"_status: **{self.status}** · {len(self.chunks)} results · "
                f"{self.duration_ms / 1000:.1f}s · ${self.cost_estimate_usd:.4f}_"
            )
            if self.quality_warning:
                out.append(f"\n> ⚠️ {self.quality_warning}")
            out.append("")
        for i, c in enumerate(self.chunks, 1):
            line = f"### {i}. [{c.title}]({c.source_url})"
            if c.site:
                line += f" — `{c.site}`"
            out.append(line)
            if c.metadata.get("date"):
                out.append(f"_{c.metadata['date']}_")
            if c.metadata.get("author"):
                out.append(f"by {c.metadata['author']}")
            body = (c.snippet or c.content or "").strip()
            if body:
                out.append("")
                out.append(body[:600])
            out.append("")
        return "\n".join(out).rstrip() + "\n"

    def to_json(self, *, indent: int | None = 2) -> str:
        """JSON dump including all fields."""
        return self.model_dump_json(indent=indent)

    def to_dict(self) -> dict:
        return self.model_dump()
