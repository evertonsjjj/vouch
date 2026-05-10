"""Extraction heuristics."""

from __future__ import annotations

from curio import Site
from curio.extraction.trafilatura import to_chunks

_SAMPLE = """
<html><body>
  <article>
    <a href="/posts/one">First post about transformers</a>
    <p>A short summary about the post.</p>
  </article>
  <article>
    <a href="https://example.com/posts/two">Second post on attention</a>
    <p>Another short body.</p>
  </article>
  <a href="https://other.com/foo">Off-domain link</a>
</body></html>
"""


def test_to_chunks_picks_card_anchors():
    site = Site(url="example.com")
    chunks = to_chunks(_SAMPLE, source_url="https://example.com/", site=site)
    titles = {c.title for c in chunks}
    assert "First post about transformers" in titles
    assert "Second post on attention" in titles
    # Off-domain link should not appear in card-mode results.
    assert all("other.com" not in c.source_url for c in chunks)


def test_to_chunks_handles_empty_html():
    chunks = to_chunks("<html></html>", source_url="https://x.com/", site=Site(url="x.com"))
    assert isinstance(chunks, list)
