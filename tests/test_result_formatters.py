"""Result formatting helpers — to_markdown, to_json, to_dict."""

from __future__ import annotations

import json

from curio.models import Chunk, SearchResult


def _result() -> SearchResult:
    return SearchResult(
        query="LLM benchmarks",
        chunks=[
            Chunk(
                source_url="https://arxiv.org/abs/2401.12345",
                site="arxiv.org",
                title="A benchmark for LLMs",
                snippet="We propose a comprehensive benchmark.",
                metadata={"date": "2024-01-15", "author": "Smith et al."},
            ),
            Chunk(
                source_url="https://huggingface.co/models/llama",
                site="huggingface.co",
                title="Llama 3 instruct",
                snippet="A fine-tuned instruction model.",
            ),
        ],
        duration_ms=1234.5,
        cost_estimate_usd=0.0012,
        status="ok",
    )


def test_to_markdown_includes_title_url_and_meta():
    md = _result().to_markdown()
    assert "# Search results for: *LLM benchmarks*" in md
    assert "arxiv.org" in md
    assert "[A benchmark for LLMs](https://arxiv.org/abs/2401.12345)" in md
    assert "Smith et al." in md
    assert "1.2s" in md or "1.23s" in md


def test_to_markdown_skip_meta():
    md = _result().to_markdown(include_meta=False)
    assert "status" not in md.lower()
    assert "[A benchmark for LLMs]" in md


def test_quality_warning_renders():
    r = _result()
    r.quality_warning = "results look like nav links"
    md = r.to_markdown()
    assert "nav links" in md
    txt = r.to_text()
    assert "warning" in txt.lower()


def test_to_json_round_trip():
    r = _result()
    parsed = json.loads(r.to_json())
    assert parsed["query"] == "LLM benchmarks"
    assert len(parsed["chunks"]) == 2
    assert parsed["chunks"][0]["site"] == "arxiv.org"


def test_to_dict():
    r = _result()
    d = r.to_dict()
    assert d["query"] == "LLM benchmarks"
    assert d["status"] == "ok"


def test_iter_and_len():
    r = _result()
    assert len(r) == 2
    titles = [c.title for c in r]
    assert "A benchmark for LLMs" in titles
