"""Compare heuristic-only vs heuristic+LLM-fallback extraction quality.

Hits 4 sites that gave bad heuristic titles in the previous run
(huggingface.co, developer.mozilla.org, github.com, pypi.org) and shows
side-by-side what the LLM fallback recovers.

Run:
    python examples/test_llm_extract_quality.py
"""

from __future__ import annotations

import io
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from vouch import SearchEngine, Site

# Sites that previously returned junk titles like "Pricing" / "Advertise with us".
SITES = [
    Site(
        "huggingface.co",
        category="ML models and datasets",
        description="Open-source ML models, datasets, benchmarks.",
        tags=["ml", "ai", "models"],
        search_url_template="/models?search={query}",
    ),
    Site(
        "developer.mozilla.org",
        category="web docs",
        description="MDN — official HTML/CSS/JS documentation.",
        tags=["web", "docs"],
        search_url_template="/en-US/search?q={query}",
    ),
    Site(
        "github.com",
        category="source code",
        description="Repositories, libraries, frameworks.",
        tags=["code", "dev"],
        search_url_template="/search?q={query}&type=repositories",
    ),
    Site(
        "pypi.org",
        category="Python packages",
        description="Official Python package index.",
        tags=["python", "packages"],
        search_url_template="/search/?q={query}",
    ),
]

QUERIES = [
    ("huggingface.co", "llama 3 instruct"),
    ("developer.mozilla.org", "javascript event loop"),
    ("github.com", "fastapi tutorial"),
    ("pypi.org", "pandas dataframe"),
]


def show_chunks(label: str, chunks):
    print(f"  {label}: {len(chunks)} chunks")
    for c in chunks[:5]:
        title = c.title[:60]
        url = c.source_url
        if len(url) > 75:
            url = url[:72] + "..."
        print(f"    • {title}")
        print(f"      {url}")


def _build_engine(cache_dir: str) -> SearchEngine:
    e = SearchEngine(
        llm="ollama/qwen2.5:7b",
        router_strategy="all",
        cache_dir=cache_dir,
    )
    for s in SITES:
        e.add(s, replace=True)
    return e


def _strip_llm_from_adapter(engine: SearchEngine):
    """Wrap engine.build_adapter so the adapter never gets the LLM client.

    This forces heuristic-only extraction without breaking the engine itself.
    """
    import vouch.engine as eng_mod

    orig = eng_mod.build_adapter

    def _no_llm(site, config, *, llm=None, selector_cache=None):
        return orig(site, config, llm=None, selector_cache=selector_cache)

    eng_mod.build_adapter = _no_llm
    return orig


def _restore(engine: SearchEngine, orig):
    import vouch.engine as eng_mod

    eng_mod.build_adapter = orig


def main():
    engine_llm = _build_engine("./test-cache-quality")
    engine_heur = _build_engine("./test-cache-heur")

    def fmt(secs: float) -> str:
        return f"{secs:.1f}s"

    for site_url, query in QUERIES:
        print(f"\n=== {site_url} :: {query!r} ===")

        # 1) heuristic-only run
        orig = _strip_llm_from_adapter(engine_heur)
        try:
            t0 = time.perf_counter()
            r_heur = engine_heur.search(query, sites=[site_url], depth=1, max_results=5, timeout=15)
            t_heur = time.perf_counter() - t0
        finally:
            _restore(engine_heur, orig)

        # 2) heuristic + LLM fallback
        t0 = time.perf_counter()
        r_llm = engine_llm.search(query, sites=[site_url], depth=1, max_results=5, timeout=15)
        t_llm = time.perf_counter() - t0

        print(f"  heuristic only      ({fmt(t_heur)})")
        show_chunks("    →", r_heur.chunks)
        print(f"  heuristic + LLM fallback ({fmt(t_llm)})")
        show_chunks("    →", r_llm.chunks)

        # Second run: cache should make the LLM run as fast as heuristic.
        t0 = time.perf_counter()
        r_llm_cached = engine_llm.search(
            query, sites=[site_url], depth=1, max_results=5, timeout=15
        )
        t_llm_cached = time.perf_counter() - t0
        print(f"  LLM-cached replay   ({fmt(t_llm_cached)}) — same site, second call")
        show_chunks("    →", r_llm_cached.chunks)

    print("\n" + "=" * 70)
    print(f"LLM total tokens used: {engine_llm._llm.tokens}")
    print(f"LLM total cost: ${engine_llm._llm.cost_usd:.4f} (Ollama → $0)")
    print(f"selector_cache after run: {engine_llm.cache_stats()}")


if __name__ == "__main__":
    main()
