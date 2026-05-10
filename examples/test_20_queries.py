"""20-query smoke test: 10 PT + 10 EN across 7 curated sites.

Run from project root:
    python examples/test_20_queries.py

Uses Ollama qwen2.5:7b for routing — cost is $0, latency depends on hardware.
"""

from __future__ import annotations

import io
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from curio import SearchEngine, Site

# ---- Catalog ---------------------------------------------------------------

SITES = [
    Site(
        "arxiv.org",
        category="academic ML/AI papers",
        description="Preprints in CS, ML, AI, math, physics — primary source for ML research papers.",
        tags=["research", "ml", "ai", "academic"],
        search_url_template="/search/?searchtype=all&query={query}",
    ),
    Site(
        "github.com",
        category="code repositories",
        description="Source code, libraries, frameworks, tools — primary source for any open-source code.",
        tags=["code", "dev", "open-source"],
        search_url_template="/search?q={query}&type=repositories",
    ),
    Site(
        "pypi.org",
        category="Python packages",
        description="Official Python package index — for finding installable Python libraries.",
        tags=["python", "packages", "dev"],
        search_url_template="/search/?q={query}",
    ),
    Site(
        "huggingface.co",
        category="ML models and datasets",
        description="Repository of open-source ML models, datasets, and benchmarks.",
        tags=["ml", "ai", "models"],
        search_url_template="/models?search={query}",
    ),
    Site(
        "developer.mozilla.org",
        category="web development docs",
        description="MDN Web Docs — official documentation for HTML, CSS, JavaScript, web APIs.",
        tags=["web", "frontend", "javascript", "docs"],
        search_url_template="/en-US/search?q={query}",
    ),
    Site(
        "crates.io",
        category="Rust packages",
        description="Official Rust package registry — for finding installable Rust crates.",
        tags=["rust", "packages", "dev"],
        search_url_template="/search?q={query}",
    ),
    Site(
        "npmjs.com",
        category="JavaScript / Node.js packages",
        description="Official npm registry — JavaScript and Node.js libraries.",
        tags=["javascript", "node", "packages", "dev"],
        search_url_template="/search?q={query}",
    ),
]

PT_QUERIES = [
    "explicação sobre arquitetura transformer machine learning",
    "biblioteca python para deep learning",
    "história da inteligência artificial",
    "como funciona retrieval augmented generation RAG",
    "tutorial fastapi python web framework",
    "redes neurais convolucionais explicação",
    "framework para construir agentes LLM autônomos",
    "comparação entre modelos LLM open source",
    "como tratar exceptions em python async",
    "história do Brasil período colonial",
]

EN_QUERIES = [
    "attention is all you need transformer paper",
    "react server components explained",
    "kubernetes operator pattern best practices",
    "vector database performance benchmark",
    "rust programming language ownership rules",
    "GPT-4 architecture details",
    "diffusion models for image generation",
    "open source large language models comparison",
    "django REST framework tutorial",
    "javascript event loop how it works",
]

# ---- Run --------------------------------------------------------------------


def run():
    engine = SearchEngine(
        llm="ollama/qwen2.5:7b",
        router_strategy="llm",
        router_top_k=2,
        parallel_sites=3,
        cache_dir="./test-cache-20",
        verbose=False,
    )
    for s in SITES:
        engine.add(s, replace=True)

    rows = []
    t_global = time.perf_counter()

    def run_one(label: str, query: str):
        t0 = time.perf_counter()
        result = engine.search(query, depth=1, max_results=3, timeout=12.0)
        elapsed = time.perf_counter() - t0
        routed = ", ".join(d.site for d in result.routing_decisions)
        first = result.chunks[0].title[:60] if result.chunks else "—"
        first_url = result.chunks[0].source_url[:60] if result.chunks else ""
        rows.append((label, query[:48], routed[:40], len(result.chunks), result.status, round(elapsed, 1), first, first_url))
        symbol = {"ok": "✓", "partial": "~", "blocked": "✗"}.get(result.status, "?")
        print(f"  {symbol} [{round(elapsed):>3}s] [{result.status:>7}] route→ {routed}")
        print(f"     query: {query}")
        if result.chunks:
            print(f"     {len(result.chunks)} chunks | first: {first}")
            print(f"                 {first_url}")
        if result.errors:
            short_errs = [e.split(": GET ")[0] + (": HTTP error" if " failed:" in e else ": " + e.split(": ", 1)[-1][:80]) for e in result.errors[:2]]
            print(f"     errors: {' | '.join(short_errs)}")

    print("=" * 80)
    print("PORTUGUÊS")
    print("=" * 80)
    for i, q in enumerate(PT_QUERIES, 1):
        print(f"\n[PT-{i:02d}]")
        run_one(f"PT-{i:02d}", q)

    print("\n" + "=" * 80)
    print("ENGLISH")
    print("=" * 80)
    for i, q in enumerate(EN_QUERIES, 1):
        print(f"\n[EN-{i:02d}]")
        run_one(f"EN-{i:02d}", q)

    total = time.perf_counter() - t_global
    print("\n" + "=" * 80)
    print(f"DONE in {total/60:.1f} min  |  total tokens: {engine._llm.tokens}  |  cost: ${engine._llm.cost_usd:.4f}")
    print("=" * 80)
    print()

    print("Summary:")
    print(f"{'#':<8}{'route':<37}{'n':<4}{'status':<10}{'sec':<7}first")
    for label, q, routed, n, status, secs, first, url in rows:
        print(f"{label:<8}{routed:<37}{n:<4}{status:<10}{secs:<7}{first}")

    blocked = sum(1 for r in rows if r[4] == "blocked")
    partial = sum(1 for r in rows if r[4] == "partial")
    ok = sum(1 for r in rows if r[4] == "ok")
    avg = sum(r[5] for r in rows) / len(rows)
    avg_chunks = sum(r[3] for r in rows) / len(rows)
    print(f"\n{ok} ok / {partial} partial / {blocked} blocked  |  mean {avg:.1f}s, {avg_chunks:.1f} chunks/query")
    print(f"site routing distribution:")
    from collections import Counter

    counter = Counter()
    for r in rows:
        for s in r[2].split(", "):
            if s:
                counter[s] += 1
    for site, n in counter.most_common():
        print(f"   {site:<25} {n} times")


if __name__ == "__main__":
    run()
