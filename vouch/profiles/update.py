"""Fetch and cache the community profile registry.

The community registry lives at::

    https://raw.githubusercontent.com/evertonsjjj/vouch-profiles/main/profiles.yaml

(Or whatever URL is configured via ``VOUCH_PROFILES_URL`` / the
``--source`` flag to ``vouch profiles update``.)

The fetched YAML is saved to ``~/.vouch/profiles_remote.yaml`` and merged
on top of the bundled ``builtin.yaml`` whenever :func:`load_user_registry`
is called.

This module is deliberately tiny — it's just an HTTP fetch + YAML round-trip
with a few politeness affordances (ETag/If-Modified-Since, timeout, retries).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from .registry import ProfileRegistry

log = logging.getLogger("vouch.profiles.update")

DEFAULT_URL = os.environ.get(
    "VOUCH_PROFILES_URL",
    "https://raw.githubusercontent.com/evertonsjjj/vouch-profiles/main/profiles.yaml",
)

CACHE_FILE = (
    Path(os.environ.get("VOUCH_HOME", str(Path.home() / ".vouch"))) / "profiles_remote.yaml"
)
META_FILE = CACHE_FILE.with_suffix(".meta.yaml")


# ----------------------------------------------------------------------
# Fetch
# ----------------------------------------------------------------------


def update_profiles(
    *,
    url: str | None = None,
    cache_path: Path | None = None,
    timeout: float = 10.0,
    force: bool = False,
) -> dict:
    """Download the latest community registry. Returns a summary dict.

    Honors HTTP caching: if the remote ``ETag`` (or ``Last-Modified``)
    matches the locally cached one, the on-disk YAML is left untouched and
    the returned summary has ``updated=False``. Pass ``force=True`` to skip
    that check.

    Network failures don't raise — they return ``status="error"`` with the
    exception in the summary, so callers can keep working with the bundled
    fallback.
    """
    url = url or DEFAULT_URL
    target = cache_path or CACHE_FILE
    target.parent.mkdir(parents=True, exist_ok=True)

    headers = {"User-Agent": "vouch-profiles/1.0"}
    meta: dict = _load_meta()
    if not force:
        if meta.get("etag"):
            headers["If-None-Match"] = meta["etag"]
        if meta.get("last_modified"):
            headers["If-Modified-Since"] = meta["last_modified"]

    summary: dict = {"url": url, "status": "unknown", "updated": False}

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
    except Exception as e:
        summary["status"] = "error"
        summary["error"] = f"{type(e).__name__}: {e}"
        return summary

    if resp.status_code == 304:
        summary["status"] = "not_modified"
        summary["profiles"] = _count_profiles(target)
        return summary

    if resp.status_code != 200:
        summary["status"] = "http_error"
        summary["http_status"] = resp.status_code
        return summary

    # Validate YAML before overwriting the cache so a bad upstream doesn't
    # corrupt the user's local state.
    try:
        parsed = yaml.safe_load(resp.text) or {}
        n_profiles = len(parsed.get("profiles") or [])
    except yaml.YAMLError as e:
        summary["status"] = "parse_error"
        summary["error"] = str(e)
        return summary

    target.write_text(resp.text, encoding="utf-8")
    _save_meta(
        {
            "etag": resp.headers.get("ETag"),
            "last_modified": resp.headers.get("Last-Modified"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "profiles": n_profiles,
        }
    )
    summary["status"] = "ok"
    summary["updated"] = True
    summary["profiles"] = n_profiles
    return summary


def _load_meta() -> dict:
    if not META_FILE.exists():
        return {}
    try:
        return yaml.safe_load(META_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _save_meta(meta: dict) -> None:
    try:
        META_FILE.parent.mkdir(parents=True, exist_ok=True)
        META_FILE.write_text(yaml.safe_dump(meta, sort_keys=True), encoding="utf-8")
    except Exception as e:
        log.warning("Could not save profile meta: %s", e)


def _count_profiles(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return len(data.get("profiles") or [])
    except Exception:
        return 0


# ----------------------------------------------------------------------
# Merging into the live registry
# ----------------------------------------------------------------------


def load_user_registry(cache_path: Path | None = None) -> ProfileRegistry | None:
    """Return a :class:`ProfileRegistry` from the locally cached YAML, or None."""
    path = cache_path or CACHE_FILE
    if not path.exists():
        return None
    try:
        return ProfileRegistry.from_yaml(path)
    except Exception as e:
        log.warning("Could not load cached remote profiles: %s", e)
        return None


__all__ = ["DEFAULT_URL", "load_user_registry", "update_profiles"]
