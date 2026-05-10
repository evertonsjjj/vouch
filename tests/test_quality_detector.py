"""Quality detector — when to escalate to LLM extraction."""

from __future__ import annotations

from farol.extraction.llm_extract import looks_low_quality
from farol.models import Chunk


def _chunk(url: str, title: str = "Pretty long real result title") -> Chunk:
    return Chunk(source_url=url, site="example.com", title=title)


def test_megamenu_detected():
    chunks = [
        _chunk("https://x.com/topics/python", "Python"),
        _chunk("https://x.com/topics/javascript", "JavaScript"),
        _chunk("https://x.com/topics/rust", "Rust"),
        _chunk("https://x.com/topics/go", "Go"),
        _chunk("https://x.com/topics/cpp", "C++"),
    ]
    assert looks_low_quality(chunks) is True


def test_recursive_first_chunk():
    src = "https://x.com/search?q=foo"
    chunks = [_chunk(src), _chunk("https://x.com/page/abc"), _chunk("https://x.com/page/def")]
    assert looks_low_quality(chunks, source_url=src) is True


def test_no_results_in_html_pt():
    chunks = [_chunk("https://x.com/a"), _chunk("https://x.com/b")]
    assert looks_low_quality(chunks, html="<p>Nenhum resultado encontrado.</p>") is True


def test_no_results_in_html_es():
    chunks = [_chunk("https://x.com/a"), _chunk("https://x.com/b")]
    assert looks_low_quality(chunks, html="<p>No se encontraron resultados.</p>") is True


def test_no_results_in_html_en():
    chunks = [_chunk("https://x.com/a"), _chunk("https://x.com/b")]
    assert looks_low_quality(chunks, html="<p>No results found.</p>") is True


def test_categorical_titles():
    chunks = [
        _chunk("https://x.com/a/sub", "History & Society"),
        _chunk("https://x.com/b/sub", "Science"),
        _chunk("https://x.com/c/sub", "Arts & Culture"),
        _chunk("https://x.com/d/sub", "Politics"),
    ]
    assert looks_low_quality(chunks) is True


def test_real_results_pass():
    chunks = [
        _chunk(
            f"https://x.com/papers/{i}/full",
            f"A meaningful research paper title number {i} about transformers",
        )
        for i in range(5)
    ]
    assert looks_low_quality(chunks) is False
