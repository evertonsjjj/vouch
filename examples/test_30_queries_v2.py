"""Reduced v2 benchmark: 30 queries (5 per category × 6 categories).

Same catalog as test_90_queries.py, same query lists (truncated to first 5).
Compares apples-to-apples with the v1 baseline by running the same first 5
queries from each category.
"""

from __future__ import annotations

import io
import sys
import time
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from curio import SearchEngine, Site

SITES = [
    Site(
        "arxiv.org",
        category="academic ML/AI papers",
        description="Preprints in CS, ML, AI, math, physics — primary source for academic research.",
        tags=["research", "ml", "ai"],
        search_url_template="/search/?searchtype=all&query={query}",
    ),
    Site(
        "github.com",
        category="open-source code",
        description="Source code, libraries, frameworks, tools.",
        tags=["code", "dev"],
        search_url_template="/search?q={query}&type=repositories",
    ),
    Site(
        "huggingface.co",
        category="ML models and datasets",
        description="Repository of ML models, datasets, benchmarks.",
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
        description="Conteúdo jurídico, leis, tributário, fiscal.",
        tags=["legal", "tributario", "br", "pt"],
        search_url_template="/busca?q={query}",
    ),
    Site(
        "gov.uk",
        category="UK government",
        description="HMRC, VAT, business, tax UK.",
        tags=["gov", "tax", "uk"],
        search_url_template="/search/all?keywords={query}",
    ),
    Site(
        "agenciatributaria.es",
        category="Hacienda España",
        description="Agencia Tributaria — IRPF, IVA, autónomos.",
        tags=["tax", "es"],
        search_url_template="/AEAT.search?p_q={query}",
    ),
    Site(
        "britannica.com",
        category="enciclopédia",
        description="Encyclopædia Britannica.",
        tags=["encyclopedia"],
        search_url_template="/search?query={query}",
    ),
    Site(
        "folha.uol.com.br",
        category="jornal BR",
        description="Folha de São Paulo — notícias.",
        tags=["news", "br"],
        search_url_template="/busca/?q={query}",
    ),
    Site(
        "elpais.com",
        category="periódico ES",
        description="El País — noticias.",
        tags=["news", "es"],
        search_url_template="/buscador/?q={query}",
    ),
]

PT_TAX = [
    "imposto de renda pessoa física 2026 declaração",
    "tabela ISS São Paulo serviços alíquota",
    "ICMS tributação interestadual diferencial",
    "MEI faturamento limite anual 2026",
    "Simples Nacional anexo III alíquota",
]
EN_TAX = [
    "IRS form 1040 individual income tax",
    "capital gains tax US 2026 long term",
    "tax deduction self employed home office",
    "estimated quarterly tax payment IRS",
    "401k contribution limit 2026",
]
ES_TAX = [
    "declaración renta IRPF 2026 España",
    "modelo 303 IVA trimestral autónomo",
    "autónomo cuota Seguridad Social tarifa plana",
    "tributación criptomonedas España 2026",
    "deducción vivienda habitual hipoteca",
]
PT_GEN = [
    "história da República Velha Brasil",
    "biografia Machado de Assis escritor",
    "fórmula química água oxigenada uso",
    "como fazer feijoada tradicional receita",
    "treino academia hipertrofia muscular iniciante",
]
EN_GEN = [
    "history of the Roman Empire fall",
    "Shakespeare Hamlet analysis themes",
    "DNA replication process biology",
    "Italian carbonara recipe traditional",
    "HIIT cardio workout routine beginner",
]
ES_GEN = [
    "historia España Reconquista cronología",
    "Gabriel García Márquez novelas Cien Años",
    "ADN replicación proceso biología molecular",
    "paella valenciana receta tradicional",
    "rutina entrenamiento gimnasio fuerza principiante",
]

ALL = (
    [("PT-TAX", q) for q in PT_TAX]
    + [("EN-TAX", q) for q in EN_TAX]
    + [("ES-TAX", q) for q in ES_TAX]
    + [("PT-GEN", q) for q in PT_GEN]
    + [("EN-GEN", q) for q in EN_GEN]
    + [("ES-GEN", q) for q in ES_GEN]
)


LOG_PATH = "./test-cache-30v2/run.log"


def _writeln(line: str) -> None:
    """Append a line to LOG_PATH and to stdout, flushing both."""
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    except FileNotFoundError:
        import os

        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()


def main():
    engine = SearchEngine(
        llm="ollama/qwen2.5:7b",
        router_strategy="llm",
        router_top_k=2,
        parallel_sites=2,
        cache_dir="./test-cache-30v2",
        auto_resolve_dns=True,
        auto_escalate_adapter=True,
    )
    import os
    os.makedirs("./test-cache-30v2", exist_ok=True)
    open(LOG_PATH, "w", encoding="utf-8").close()  # truncate

    for s in SITES:
        try:
            engine.add(s, replace=True)
        except Exception as e:
            _writeln(f"add {s.url} failed: {e}")

    rows = []
    t_global = time.perf_counter()
    _writeln(f"Running {len(ALL)} queries against {len(SITES)} sites...")
    _writeln("")

    for i, (label, query) in enumerate(ALL, 1):
        t0 = time.perf_counter()
        try:
            r = engine.search(query, depth=1, max_results=3, timeout=20)
        except Exception as e:
            elapsed = time.perf_counter() - t0
            _writeln(f"[{i:>2}] {label} ERROR {elapsed:.1f}s: {type(e).__name__}: {e}")
            rows.append((i, label, query[:48], "", 0, "error", round(elapsed, 1), ""))
            continue
        elapsed = time.perf_counter() - t0
        routed = ", ".join(d.site for d in r.routing_decisions)
        first = r.chunks[0].title[:55] if r.chunks else "—"
        rows.append((i, label, query[:48], routed[:40], len(r.chunks), r.status, round(elapsed, 1), first))
        sym = {"ok": "✓", "partial": "~", "blocked": "✗"}.get(r.status, "?")
        _writeln(f"[{i:>2}] {label} {sym} {elapsed:>4.1f}s chunks={len(r.chunks)} | route={routed} | first: {first}")

    total = time.perf_counter() - t_global
    _writeln("")
    _writeln("=" * 90)
    _writeln(f"DONE in {total/60:.1f} min  |  tokens: {engine._llm.tokens}  |  cost: ${engine._llm.cost_usd:.4f}")
    _writeln("")

    by_status = Counter(r[5] for r in rows)
    _writeln("Status breakdown:")
    for s, n in by_status.most_common():
        _writeln(f"  {s:<10} {n}/{len(rows)}")
    _writeln("")

    _writeln("Per-category:")
    for cat in ["PT-TAX", "EN-TAX", "ES-TAX", "PT-GEN", "EN-GEN", "ES-GEN"]:
        sub = [r for r in rows if r[1] == cat]
        ok = sum(1 for r in sub if r[5] == "ok")
        pa = sum(1 for r in sub if r[5] == "partial")
        bl = sum(1 for r in sub if r[5] == "blocked")
        avg = sum(r[6] for r in sub) / max(len(sub), 1)
        nch = sum(r[4] for r in sub) / max(len(sub), 1)
        _writeln(f"  {cat}: ok={ok} partial={pa} blocked={bl} | mean {avg:.1f}s, {nch:.1f} chunks/q")

    _writeln("")
    _writeln("Cache state per site:")
    for d, s in engine.cache_stats().items():
        full = engine.selector_cache.get(d) or {}
        css = "css✓" if full.get("result_selectors") else "css×"
        url_pat = full.get("result_url_contains") or ""
        _writeln(f"  {d:<35} tier={full.get('working_tier','?'):<8} {css} url_pat={url_pat!r:<15} hits={s.get('hits')}")

    import json
    with open("./test-cache-30v2/results.json", "w", encoding="utf-8") as f:
        json.dump([dict(zip(["i","label","query","routed","chunks","status","secs","first"], r)) for r in rows], f, ensure_ascii=False, indent=2)
    _writeln("")
    _writeln("Results JSON: ./test-cache-30v2/results.json")


if __name__ == "__main__":
    main()
