"""Runtime configuration for SearchEngine."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

RouterStrategy = Literal["llm", "embedding", "all", "tags"]
Behavior = Literal["natural", "stealth", "external"]
TypingSpeed = Literal["fast", "natural", "slow"]


def _expand(p: str | Path) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(p)))).resolve()


class EngineConfig(BaseModel):
    """All knobs that control a SearchEngine. Most have sane defaults."""

    # LLM ------------------------------------------------------------------
    llm: str | list[str] = "ollama/qwen2.5:14b"
    router_llm: str | None = None
    vision_llm: str | None = None
    api_keys: dict[str, str] | None = None

    # Routing --------------------------------------------------------------
    router_strategy: RouterStrategy = "llm"
    router_top_k: int = 3
    router_explain: bool = False

    # Search ---------------------------------------------------------------
    default_depth: int = 1
    parallel_sites: int = 3

    # Browser --------------------------------------------------------------
    default_behavior: Behavior = "natural"
    humanize: bool = True
    typing_speed: TypingSpeed = "natural"
    headless: bool = True
    business_hours_only: bool = False

    # Caching --------------------------------------------------------------
    cache_dir: Path = Field(default_factory=lambda: _expand("~/.farol"))
    cache_ttl_days: int = 30

    # Politeness -----------------------------------------------------------
    respect_robots_txt: bool = True
    default_rate_limit: str = "2/min"
    user_agent: str | None = None

    # Captcha (only used if vision_llm set) --------------------------------
    captcha_min_confidence: float = 0.7
    captcha_max_attempts: int = 2

    # Resilience -----------------------------------------------------------
    auto_resolve_dns: bool = False
    auto_escalate_adapter: bool = True
    auto_probe_on_add: bool = False
    probe_queries: int = 1  # how many probe queries to run when auto-probing

    # Misc -----------------------------------------------------------------
    verbose: bool = False
    request_timeout: float = 30.0

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("cache_dir", mode="before")
    @classmethod
    def _expand_cache(cls, v):
        return _expand(v) if v else _expand("~/.farol")

    @field_validator("default_depth")
    @classmethod
    def _depth_range(cls, v):
        if not 0 <= v <= 3:
            raise ValueError("depth must be in [0, 3]")
        return v

    @field_validator("router_top_k")
    @classmethod
    def _topk_positive(cls, v):
        if v < 1:
            raise ValueError("router_top_k must be >= 1")
        return v

    def effective_router_llm(self) -> str | list[str]:
        return self.router_llm or self.llm

    def cache_path(self, name: str) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        return self.cache_dir / name
