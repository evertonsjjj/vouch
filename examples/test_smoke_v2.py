"""Smoke test for the v2 improvements — 6 queries (1 per category) to validate.

Runs against the same catalog as test_90_queries.py but only 1 query per
language/category. Used to verify auto-escalation, CSS selector pinning,
and DNS resolution all work end-to-end before committing to the full 90.
"""

from __future__ import annotations

import io
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from vouch import SearchEngine, Site

SITES = [
    Site(
        "arxiv.org",
        category="academic ML/AI papers",
        description="Preprints in CS, ML, AI, math, physics — primary source for academic ML/AI research.",
        tags=["research", "ml", "ai"],
        search_url_template="/search/?searchtype=all&query={query}",
    ),
    Site(
        "github.com",
        category="open-source code",
        description="Code repositories, libraries, frameworks.",
        tags=["code", "dev"],
        search_url_template="/search?q={query}&type=repositories",
    ),
    Site(
        "huggingface.co",
        category="ML models",
        description="Repository of ML models and datasets.",
        tags=["ml", "ai", "models"],
        search_url_template="/models?search={query}",
    ),
    Site(
        "pypi.org",
        category="Python packages",
        description="Official Python package index.",
        tags=["python", "dev"],
        search_url_template="/search/?q={query}",
    ),
    Site(
        "jusbrasil.com.br",
        category="legislação BR",
        description="Conteúdo jurídico, leis, decisões, artigos sobre direito tributário, fiscal, previdenciário e civil.",
        tags=["legal", "tributario", "br", "pt"],
        search_url_template="/busca?q={query}",
    ),
    Site(
        "gov.uk",
        category="UK gov tax",
        description="UK government — HMRC, VAT, business, tax.",
        tags=["gov", "tax", "uk"],
        search_url_template="/search/all?keywords={query}",
    ),
    Site(
        "agenciatributaria.es",
        category="Hacienda España",
        description="Agencia Tributaria — IRPF, IVA, autónomos.",
        tags=["tax", "es", "hacienda"],
        search_url_template="/AEAT.search?p_q={query}",
    ),
    Site(
        "britannica.com",
        category="enciclopédia geral EN",
        description="Encyclopædia Britannica — knowledge, history.",
        tags=["encyclopedia", "en"],
        search_url_template="/search?query={query}",
    ),
    Site(
        "folha.uol.com.br",
        category="jornal BR",
        description="Folha de São Paulo — notícias.",
        tags=["news", "br", "pt"],
        search_url_template="/busca/?q={query}",
    ),
    Site(
        "elpais.com",
        category="periódico ES",
        description="El País — noticias generales.",
        tags=["news", "es"],
        search_url_template="/buscador/?q={query}",
    ),
]

QUERIES = [
    ("PT-TAX", "imposto de renda pessoa física 2026 declaração"),
    ("EN-TAX", "IRS form 1040 individual income tax"),
    ("ES-TAX", "declaración renta IRPF 2026 España"),
    ("PT-GEN", "história da República Velha Brasil"),
    ("EN-GEN", "history of the Roman Empire fall"),
    ("ES-GEN", "Gabriel García Márquez novelas Cien Años"),
]


def main():
    engine = SearchEngine(
        llm="ollama/qwen2.5:7b",
        router_strategy="llm",
        router_top_k=2,
        parallel_sites=2,
        cache_dir="./test-cache-smoke",
        auto_resolve_dns=True,
        auto_escalate_adapter=True,
    )
    for s in SITES:
        try:
            engine.add(s, replace=True)
        except Exception as e:
            print(f"add {s.url} failed: {e}")

    print(f"Catalog: {[s.url for s in engine.list_sites()]}")
    print()

    t_global = time.perf_counter()
    for label, query in QUERIES:
        print(f"=== {label}: {query!r} ===")
        t0 = time.perf_counter()
        result = engine.search(query, depth=1, max_results=3, timeout=20)
        elapsed = time.perf_counter() - t0
        print(f"  status={result.status} in {elapsed:.1f}s | chunks={len(result.chunks)}")
        print(f"  routed: {[d.site for d in result.routing_decisions]}")
        for c in result.chunks[:3]:
            url = c.source_url
            if len(url) > 70:
                url = url[:67] + "..."
            print(f"    • {c.title[:70]}")
            print(f"      {url}")
            if c.snippet:
                print(f"      \"{c.snippet[:100]}\"")
        if result.errors:
            for err in result.errors[:2]:
                print(f"    [err] {err.split(': GET ')[0][:80]}")
        print()

    print(f"Total: {(time.perf_counter()-t_global)/60:.1f} min")
    print(f"Tokens: {engine._llm.tokens}")
    print(f"Cost: ${engine._llm.cost_usd:.4f}")
    print(f"Cache: {engine.cache_stats()}")


if __name__ == "__main__":
    main()
