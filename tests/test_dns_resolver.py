"""DNS resolver — focused on the candidate-list logic; network calls are skipped."""

from __future__ import annotations

from farol.dns_resolver import _candidate_hosts, resolve_canonical_host


def test_candidate_list_for_es_domain():
    cands = _candidate_hosts("agenciatributaria.es")
    assert "agenciatributaria.es" in cands
    assert "www.agenciatributaria.es" in cands
    assert "sede.agenciatributaria.es" in cands
    assert "sede.agenciatributaria.gob.es" in cands


def test_candidate_list_for_br_domain():
    cands = _candidate_hosts("planalto.com.br")
    assert "planalto.com.br" in cands
    assert "www.planalto.com.br" in cands


def test_candidate_strips_www_prefix():
    cands = _candidate_hosts("www.foo.com")
    assert cands[0] == "foo.com"
    assert "www.foo.com" in cands


def test_resolve_falls_back_to_input_on_failure(monkeypatch):
    """When nothing resolves, return the original domain so caller fails clean."""
    from farol import dns_resolver

    monkeypatch.setattr(dns_resolver, "_dns_resolves", lambda *_: False)
    monkeypatch.setattr(dns_resolver, "_http_ok", lambda *_, **__: False)
    assert resolve_canonical_host("does-not-exist-zzz.test") == "does-not-exist-zzz.test"
