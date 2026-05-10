"""Plugin discovery — entry_points wiring without installing real packages.

Patches :func:`importlib.metadata.entry_points` to return fake plugins so we
can exercise the loader logic without publishing test fixtures.
"""

from __future__ import annotations

from unittest.mock import patch

from farol import plugins


def _fake_ep(name: str, loaded):
    """Build a stub that behaves like an importlib.metadata.EntryPoint."""

    class _EP:
        def __init__(self):
            self.name = name

        def load(self):
            return loaded

    return _EP()


def test_find_exact_match_wins():
    eps = [
        _fake_ep("*", lambda **k: "catchall"),
        _fake_ep("*.gov.br", lambda **k: "br_suffix"),
        _fake_ep("arxiv.org", lambda **k: "arxiv_exact"),
    ]
    with patch("farol.plugins._load", return_value=eps):
        out = plugins.find_adapter_factory("arxiv.org")
        assert callable(out)
        assert out() == "arxiv_exact"


def test_suffix_match_for_br_gov():
    eps = [
        _fake_ep("*.gov.br", lambda **k: "br_suffix"),
        _fake_ep("*", lambda **k: "catchall"),
    ]
    with patch("farol.plugins._load", return_value=eps):
        out = plugins.find_adapter_factory("cvm.gov.br")
        assert out() == "br_suffix"


def test_longest_suffix_wins():
    eps = [
        _fake_ep("*.br", lambda **k: "br_short"),
        _fake_ep("*.gov.br", lambda **k: "br_long"),
    ]
    with patch("farol.plugins._load", return_value=eps):
        out = plugins.find_adapter_factory("receita.gov.br")
        assert out() == "br_long"


def test_wildcard_fallback():
    eps = [_fake_ep("*", lambda **k: "fallback")]
    with patch("farol.plugins._load", return_value=eps):
        assert plugins.find_adapter_factory("any.com")() == "fallback"


def test_no_match_returns_none():
    eps = [_fake_ep("arxiv.org", lambda **k: "x")]
    with patch("farol.plugins._load", return_value=eps):
        assert plugins.find_adapter_factory("github.com") is None


def test_list_adapter_plugins_sorted():
    eps = [
        _fake_ep("z.com", lambda: None),
        _fake_ep("a.com", lambda: None),
        _fake_ep("m.com", lambda: None),
    ]
    with patch("farol.plugins._load", return_value=eps):
        assert plugins.list_adapter_plugins() == ["a.com", "m.com", "z.com"]


def test_plugin_failure_does_not_block_build_adapter():
    """If a plugin's load() raises, build_adapter should fall back to defaults."""
    from farol import Site
    from farol.adapters import build_adapter
    from farol.config import EngineConfig

    class _BrokenEP:
        name = "github.com"

        def load(self):
            raise RuntimeError("plugin is broken")

    with patch("farol.plugins._load", return_value=[_BrokenEP()]):
        site = Site("github.com", search_url_template="/search?q={query}")
        adapter = build_adapter(site, EngineConfig())
        # Should fall through to HTTPAdapter via the template path
        assert adapter.__class__.__name__ == "HTTPAdapter"


def test_plugin_factory_invoked_with_engine_kwargs():
    """build_adapter should pass site/config/llm/cache/pool to the plugin."""
    from farol import Site
    from farol.adapters import build_adapter
    from farol.config import EngineConfig

    received: dict = {}

    def _factory(**kwargs):
        received.update(kwargs)

        class _Stub:
            def search(self, ctx):
                return []

            def close(self):
                pass

        return _Stub()

    eps = [_fake_ep("arxiv.org", _factory)]
    with patch("farol.plugins._load", return_value=eps):
        site = Site("arxiv.org")
        build_adapter(site, EngineConfig(), llm="sentinel-llm", selector_cache="cache-sentinel")
        assert received["site"].url == "arxiv.org"
        assert received["llm"] == "sentinel-llm"
        assert received["selector_cache"] == "cache-sentinel"


def test_router_plugin_lookup():
    class _Cls:
        pass

    eps = [_fake_ep("pinecone", _Cls)]
    with patch("farol.plugins._load", return_value=eps):
        assert plugins.find_router_factory("pinecone") is _Cls
        assert plugins.find_router_factory("nonexistent") is None
