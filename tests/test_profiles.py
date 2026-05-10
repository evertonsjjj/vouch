"""Profile registry — load builtin, lookup, list, import via CLI."""

from __future__ import annotations

import pytest

from curio import Site, get_profile, list_profiles
from curio.profiles import ProfileRegistry


def test_builtin_loads_at_least_20_profiles():
    domains = list_profiles()
    assert len(domains) >= 20, f"expected 20+ bundled profiles, got {len(domains)}"
    # Spot-check a few essentials
    for must_have in ("arxiv.org", "github.com", "huggingface.co", "pypi.org"):
        assert must_have in domains


def test_get_profile_returns_site():
    s = get_profile("arxiv.org")
    assert isinstance(s, Site)
    assert s.url == "arxiv.org"
    assert s.search_url_template
    assert "arxiv" in (s.description or "").lower() or s.tags


def test_get_profile_normalizes_url_input():
    s1 = get_profile("github.com")
    s2 = get_profile("https://github.com/")
    s3 = get_profile("GITHUB.COM")
    assert s1 and s2 and s3
    assert s1.url == s2.url == s3.url == "github.com"


def test_get_profile_unknown_returns_none():
    assert get_profile("totally-made-up-domain.test") is None


def test_registry_from_yaml_roundtrip(tmp_path):
    yaml_text = """\
profiles:
  - url: example.com
    category: testing
    description: a test profile
    tags: [test]
"""
    p = tmp_path / "p.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    reg = ProfileRegistry.from_yaml(p)
    assert "example.com" in reg.list()
    s = reg.get("example.com")
    assert s.category == "testing"


def test_registry_merge_overwrites():
    a = ProfileRegistry({"x.com": {"url": "x.com", "category": "old"}})
    b = ProfileRegistry({"x.com": {"url": "x.com", "category": "new"}})
    a.merge(b)
    assert a.get("x.com").category == "new"


@pytest.mark.parametrize("domain", ["arxiv.org", "github.com", "pypi.org", "huggingface.co"])
def test_each_known_profile_has_template(domain):
    """All ML/dev profiles should at least have a search_url_template."""
    s = get_profile(domain)
    assert s.search_url_template, f"{domain} missing search_url_template"
    assert "{query}" in s.search_url_template, f"{domain} template missing {{query}}"
