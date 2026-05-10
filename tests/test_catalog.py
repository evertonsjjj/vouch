"""Catalog persistence and Site normalization."""

from __future__ import annotations

import pytest

from farol import Catalog, Site
from farol.exceptions import CatalogError


def test_url_normalization():
    assert Site(url="https://www.cvm.gov.br/foo/bar").url == "cvm.gov.br"
    assert Site(url="cvm.gov.br").url == "cvm.gov.br"
    assert Site(url="HTTPS://CVM.GOV.BR").url == "cvm.gov.br"


def test_routing_blob_includes_metadata():
    s = Site(url="x.com", category="news", description="news site", tags=["a", "b"])
    blob = s.routing_blob()
    assert "x.com" in blob
    assert "news" in blob
    assert "a" in blob and "b" in blob


def test_add_get_remove(empty_catalog: Catalog):
    s = Site(url="example.com", category="test")
    empty_catalog.add(s)
    got = empty_catalog.get("example.com")
    assert got is not None
    assert got.url == "example.com"
    assert empty_catalog.remove("example.com") is True
    assert empty_catalog.get("example.com") is None


def test_duplicate_add_raises_unless_replace(empty_catalog):
    empty_catalog.add(Site(url="example.com"))
    with pytest.raises(CatalogError):
        empty_catalog.add(Site(url="example.com"))
    empty_catalog.add(Site(url="example.com", category="updated"), replace=True)
    assert empty_catalog.get("example.com").category == "updated"


def test_list_filter_by_tags(populated_catalog):
    devs = populated_catalog.list(only_tags=["dev"])
    urls = {s.url for s in devs}
    assert "github.com" in urls and "stackoverflow.com" in urls
    assert "cvm.gov.br" not in urls


def test_yaml_round_trip(tmp_path, populated_catalog):
    yaml_text = populated_catalog.export_yaml()
    p = tmp_path / "sites.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    fresh = Catalog(tmp_path / "fresh.db")
    fresh.load_yaml(p)
    assert {s.url for s in fresh.list()} == {s.url for s in populated_catalog.list()}


def test_normalization_lookup(populated_catalog):
    assert populated_catalog.get("https://www.github.com/whatever") is not None
