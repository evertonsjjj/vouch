"""Profile auto-update — HTTP fetch + cache merge, all offline via respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from vouch.profiles import update as updater

DUMMY_YAML = """\
profiles:
  - url: community-site.example
    category: testing
    description: a community-contributed profile
    tags: [test, community]
    search_url_template: "/search?q={query}"
  - url: another-site.example
    category: testing
"""


@pytest.fixture
def cache_path(tmp_path, monkeypatch):
    path = tmp_path / "profiles_remote.yaml"
    meta = tmp_path / "profiles_remote.meta.yaml"
    monkeypatch.setattr(updater, "CACHE_FILE", path)
    monkeypatch.setattr(updater, "META_FILE", meta)
    return path


@respx.mock
def test_first_fetch_writes_cache_and_meta(cache_path):
    respx.get("https://example.test/profiles.yaml").mock(
        return_value=httpx.Response(
            200,
            content=DUMMY_YAML,
            headers={"ETag": '"abc123"', "Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT"},
        )
    )
    summary = updater.update_profiles(url="https://example.test/profiles.yaml")
    assert summary["status"] == "ok"
    assert summary["updated"] is True
    assert summary["profiles"] == 2
    assert cache_path.exists()
    assert "community-site.example" in cache_path.read_text(encoding="utf-8")


@respx.mock
def test_second_fetch_short_circuits_on_304(cache_path):
    # First fetch — populates the cache + meta with an ETag.
    route = respx.get("https://example.test/profiles.yaml").mock(
        side_effect=[
            httpx.Response(200, content=DUMMY_YAML, headers={"ETag": '"abc123"'}),
            httpx.Response(304),
        ]
    )
    summary1 = updater.update_profiles(url="https://example.test/profiles.yaml")
    assert summary1["status"] == "ok"
    assert summary1["updated"] is True

    # Second fetch — server returns 304 Not Modified.
    summary2 = updater.update_profiles(url="https://example.test/profiles.yaml")
    assert summary2["status"] == "not_modified", f"unexpected: {summary2}"
    assert summary2["updated"] is False
    # The second request must have included our cached ETag
    second_req = route.calls[1].request
    assert second_req.headers.get("if-none-match") == '"abc123"'


@respx.mock
def test_force_skips_304_check(cache_path):
    respx.get("https://example.test/profiles.yaml").mock(
        return_value=httpx.Response(200, content=DUMMY_YAML, headers={"ETag": '"v1"'})
    )
    updater.update_profiles(url="https://example.test/profiles.yaml")
    respx.reset()

    # Even though we cached the ETag, force=True must skip the If-None-Match.
    route = respx.get("https://example.test/profiles.yaml").mock(
        return_value=httpx.Response(200, content=DUMMY_YAML, headers={"ETag": '"v2"'})
    )
    summary = updater.update_profiles(url="https://example.test/profiles.yaml", force=True)
    assert summary["status"] == "ok"
    # No If-None-Match should have been sent
    sent_request = route.calls[0].request
    assert "if-none-match" not in {k.lower() for k in sent_request.headers}


@respx.mock
def test_network_error_does_not_raise(cache_path):
    respx.get("https://example.test/profiles.yaml").mock(side_effect=httpx.ConnectError("nope"))
    summary = updater.update_profiles(url="https://example.test/profiles.yaml")
    assert summary["status"] == "error"
    assert "nope" in summary["error"]


@respx.mock
def test_invalid_yaml_does_not_overwrite_cache(cache_path):
    # Seed a good cache.
    cache_path.write_text(DUMMY_YAML, encoding="utf-8")

    bad = "this: is: not: valid: yaml: :::"
    respx.get("https://example.test/profiles.yaml").mock(
        return_value=httpx.Response(200, content=bad)
    )
    summary = updater.update_profiles(url="https://example.test/profiles.yaml")
    assert summary["status"] == "parse_error"
    # Original cache must still be intact
    assert "community-site.example" in cache_path.read_text(encoding="utf-8")


def test_load_user_registry_returns_none_when_missing(tmp_path):
    assert updater.load_user_registry(tmp_path / "nope.yaml") is None


def test_load_user_registry_parses_cache(tmp_path):
    path = tmp_path / "cache.yaml"
    path.write_text(DUMMY_YAML, encoding="utf-8")
    reg = updater.load_user_registry(path)
    assert reg is not None
    assert "community-site.example" in reg.list()
