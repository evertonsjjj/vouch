"""Profile loader — reads curated YAML, returns ready-to-use Sites."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from ..catalog import Site

log = logging.getLogger("farol.profiles")

_BUILTIN_PATH = Path(__file__).parent / "builtin.yaml"


class ProfileRegistry:
    """In-memory store of curated site profiles."""

    def __init__(self, profiles: dict[str, dict[str, Any]] | None = None):
        self._profiles: dict[str, dict[str, Any]] = profiles or {}

    @classmethod
    def builtin(cls) -> ProfileRegistry:
        if not _BUILTIN_PATH.exists():
            return cls()
        try:
            data = yaml.safe_load(_BUILTIN_PATH.read_text(encoding="utf-8")) or {}
        except Exception as e:
            log.warning("Could not read builtin profiles: %s", e)
            return cls()
        profiles = {p["url"]: p for p in (data.get("profiles") or []) if "url" in p}
        return cls(profiles)

    @classmethod
    def from_yaml(cls, path: str | Path) -> ProfileRegistry:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        profiles = {p["url"]: p for p in (data.get("profiles") or []) if "url" in p}
        return cls(profiles)

    def get(self, domain: str) -> Site | None:
        from ..catalog import _normalize_domain

        key = _normalize_domain(domain)
        raw = self._profiles.get(key)
        if not raw:
            return None
        return self._raw_to_site(raw)

    def list(self) -> list[str]:
        return sorted(self._profiles)

    def merge(self, other: ProfileRegistry) -> None:
        """In-place merge — *other* wins on conflicts."""
        self._profiles.update(other._profiles)

    @staticmethod
    def _raw_to_site(raw: dict[str, Any]) -> Site:
        # Strip profile-only keys (working_tier, result_selectors) — those go
        # into the caller's selector cache later, not the Site model.
        site_keys = {
            "url",
            "category",
            "description",
            "tags",
            "behavior",
            "rate_limit",
            "requires_login",
            "search_url_template",
        }
        site_kwargs = {k: v for k, v in raw.items() if k in site_keys}
        return Site(**site_kwargs)


_DEFAULT = ProfileRegistry.builtin()


def get_profile(domain: str) -> Site | None:
    """Return a curated Site for ``domain``, or ``None`` if no profile exists."""
    return _DEFAULT.get(domain)


def list_profiles() -> list[str]:
    """List all domains with curated profiles."""
    return _DEFAULT.list()


__all__ = ["ProfileRegistry", "get_profile", "list_profiles"]
