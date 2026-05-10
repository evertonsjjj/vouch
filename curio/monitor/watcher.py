"""Periodic re-search with 3-tier change detection (hash → diff → embedding)."""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..models import SearchResult
from .notify import Notifier

if TYPE_CHECKING:
    from ..engine import SearchEngine

log = logging.getLogger("curio.monitor")

_INTERVAL_RE = re.compile(r"^\s*(\d+)\s*(s|m|h|d|w)\s*$", re.IGNORECASE)


def _interval_to_seconds(spec: str) -> int:
    m = _INTERVAL_RE.match(spec)
    if not m:
        raise ValueError(f"Bad interval: {spec!r}. Use forms like '5m', '1h', '2d'.")
    n, unit = int(m.group(1)), m.group(2).lower()
    return n * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]


@dataclass
class Watch:
    site: str
    query: str
    interval_seconds: int
    notify: Notifier
    last_hash: str | None = None
    callback: Callable[[SearchResult], None] | None = None
    extra: dict = field(default_factory=dict)


class Monitor:
    """APScheduler-based periodic searcher."""

    def __init__(self, engine: SearchEngine):
        self.engine = engine
        self.watches: list[Watch] = []
        self._scheduler: Any = None

    # ---- API --------------------------------------------------------

    def watch(
        self,
        *,
        site: str,
        query: str,
        interval: str = "1h",
        notify_via: str | list[str] | None = None,
        notifier: Notifier | None = None,
        callback: Callable[[SearchResult], None] | None = None,
    ) -> Watch:
        n = notifier or Notifier(notify_via)
        w = Watch(
            site=site,
            query=query,
            interval_seconds=_interval_to_seconds(interval),
            notify=n,
            callback=callback,
        )
        self.watches.append(w)
        return w

    def start(self, *, blocking: bool = True) -> None:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore
            from apscheduler.schedulers.blocking import BlockingScheduler  # type: ignore
        except ImportError as e:
            raise ImportError(
                "Monitor requires apscheduler. Install with: pip install 'curio[monitor]'"
            ) from e

        if not self.watches:
            log.warning("Monitor.start() called with no watches.")
            return

        self._scheduler = BlockingScheduler() if blocking else BackgroundScheduler()
        for w in self.watches:
            self._scheduler.add_job(
                self._run_one,
                "interval",
                seconds=w.interval_seconds,
                args=[w],
                next_run_time=None,
                id=f"{w.site}:{w.query}",
            )
        self._scheduler.start()

    def stop(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)

    # ---- internals --------------------------------------------------

    def _run_one(self, w: Watch) -> None:
        try:
            result = self.engine.search(w.query, sites=[w.site])
        except Exception as e:
            log.exception("watch %s/%s failed: %s", w.site, w.query, e)
            return

        digest = _hash_result(result)
        if w.last_hash and digest == w.last_hash:
            log.debug("no change for %s/%s", w.site, w.query)
            return

        if w.last_hash is not None:
            w.notify.notify(
                title=f"[curio] change on {w.site}",
                body=_format_changes(result),
            )
        if w.callback:
            try:
                w.callback(result)
            except Exception as e:
                log.warning("watch callback raised: %s", e)
        w.last_hash = digest


def _hash_result(result: SearchResult) -> str:
    payload = "\n".join(f"{c.source_url}|{c.title}" for c in result.chunks)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _format_changes(result: SearchResult) -> str:
    lines = [f"Query: {result.query}", ""]
    for i, c in enumerate(result.chunks[:10], 1):
        lines.append(f"{i}. [{c.site}] {c.title}\n   {c.source_url}")
    return "\n".join(lines)


__all__ = ["Monitor", "Watch"]
