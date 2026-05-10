"""Find the canonical hostname for a domain the user typed.

Many real-world catalogs hit DNS issues:
  * ``agenciatributaria.es`` doesn't resolve; the real host is
    ``sede.agenciatributaria.gob.es``.
  * A user types ``foo.com`` but the site is at ``www.foo.com``.

This module probes a short list of canonical-host variants and returns the
first one that responds with a usable HTTP status. Skips the network entirely
when the input already resolves.
"""

from __future__ import annotations

import logging
import socket
from collections.abc import Iterable

import httpx

log = logging.getLogger("curio.dns")

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
    )
}


def _candidate_hosts(domain: str) -> list[str]:
    domain = domain.strip().lower().lstrip(".")
    if domain.startswith("www."):
        bare = domain[4:]
    else:
        bare = domain
    out = [
        bare,
        f"www.{bare}",
        f"sede.{bare}",
        f"agencia.{bare}",
        f"portal.{bare}",
        f"app.{bare}",
    ]
    # If domain ends with a country TLD that often has a `.gob.es` / `.gov.br`
    # extension (Spain / Brazil agencies), also try the gov-prefixed variant.
    if bare.endswith(".es"):
        root = bare.removesuffix(".es")
        out.append(f"sede.{root}.gob.es")
        out.append(f"{root}.gob.es")
    if bare.endswith(".br") and not bare.endswith(".gov.br"):
        root = bare.removesuffix(".com.br").removesuffix(".br")
        out.append(f"{root}.gov.br")
    seen: set[str] = set()
    deduped = []
    for c in out:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


def _dns_resolves(host: str) -> bool:
    try:
        socket.gethostbyname(host)
        return True
    except OSError:
        return False


def _http_ok(host: str, *, timeout: float = 6.0) -> bool:
    try:
        with httpx.Client(
            timeout=timeout, follow_redirects=True, headers=_DEFAULT_HEADERS
        ) as client:
            r = client.head(f"https://{host}")
            if r.status_code in (405, 501):
                # Servers that reject HEAD; try GET on root.
                r = client.get(f"https://{host}", timeout=timeout)
            return r.status_code < 500 and r.status_code != 404
    except Exception as e:
        log.debug("HTTP probe %s failed: %s", host, e)
        return False


def resolve_canonical_host(domain: str, *, candidates: Iterable[str] | None = None) -> str:
    """Find a hostname under *domain* that actually answers HTTP.

    Returns the original domain if probing fails (don't break the caller; just
    let them try and fail with a clearer downstream error).
    """
    pool = list(candidates) if candidates is not None else _candidate_hosts(domain)
    for host in pool:
        if not _dns_resolves(host):
            continue
        if _http_ok(host):
            log.info("Canonical host for %s: %s", domain, host)
            return host
    log.warning("Could not validate any candidate for %s; keeping original", domain)
    return domain


__all__ = ["resolve_canonical_host"]
