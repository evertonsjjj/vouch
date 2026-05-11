"""Notification fan-out. Uses Apprise when present; falls back to logging otherwise."""

from __future__ import annotations

import logging

log = logging.getLogger("vouch.monitor.notify")


class Notifier:
    """Wraps Apprise, exposing a single ``notify(title, body)`` method.

    Pass either a list of Apprise URLs (``mailto://...``, ``slack://...``) or a
    single notify-via shortcut (``"email"``, ``"slack"``, ``"discord"``,
    ``"webhook"``). Shortcut mode requires the matching env vars to be set.
    """

    def __init__(self, channels: list[str] | str | None = None):
        if isinstance(channels, str):
            channels = self._expand_shortcut(channels)
        self.channels = channels or []
        self._apprise = None
        if self.channels:
            try:
                import apprise  # type: ignore

                self._apprise = apprise.Apprise()
                for url in self.channels:
                    self._apprise.add(url)
            except ImportError:
                log.warning("apprise not installed; notifications will only be logged")

    def notify(self, title: str, body: str) -> None:
        if self._apprise:
            self._apprise.notify(title=title, body=body)
        else:
            log.info("[notify] %s\n%s", title, body)

    @staticmethod
    def _expand_shortcut(name: str) -> list[str]:
        import os

        if name == "email":
            url = os.environ.get("VOUCH_NOTIFY_EMAIL_URL")
            return [url] if url else []
        if name == "slack":
            url = os.environ.get("VOUCH_NOTIFY_SLACK_URL")
            return [url] if url else []
        if name == "discord":
            url = os.environ.get("VOUCH_NOTIFY_DISCORD_URL")
            return [url] if url else []
        if name == "webhook":
            url = os.environ.get("VOUCH_NOTIFY_WEBHOOK_URL")
            return [url] if url else []
        return [name]


__all__ = ["Notifier"]
