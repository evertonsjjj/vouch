"""90-query benchmark: 45 tax-related + 45 general, split across PT/EN/ESP.

Run from project root:
    python examples/test_90_queries.py

Output: per-query status line + summary table at end.
"""

from __future__ import annotations

import io
import sys
import time
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from farol import SearchEngine, Site

# ---- Catalog ---------------------------------------------------------------

SITES = [
    Site(
        "arxiv.org",
        category="academic ML/AI papers",
        description="Preprints in CS, ML, AI, math, physics, biology — primary source for academic ML/AI research.",
        tags=["research", "ml", "ai", "academic", "en"],
        search_url_template="/search/?searchtype=all&query={query}",
    ),
    Site(
        "github.com",
        category="open-source code",
        description="Code repositories, libraries, frameworks, tools. Primary source for any open-source software.",
        tags=["code", "dev", "open-source", "en"],
        search_url_template="/search?q={query}&type=repositories",
    ),
    Site(
        "huggingface.co",
        category="ML models and datasets",
        description="Repository of open-source machine learning models, datasets, and evaluation benchmarks.",
        tags=["ml", "ai", "models", "en"],
        search_url_template="/models?search={query}",
    ),
    Site(
        "pypi.org",
        category="Python packages",
        description="Official Python package index — for finding installable Python libraries.",
        tags=["python", "packages", "dev", "en"],
        search_url_template="/search/?q={query}",
    ),
    Site(
        "jusbrasil.com.br",
        category="legislação e tributação Brasil",
        description="Conteúdo jurídico, leis, decisões, artigos sobre direito tributário, fiscal, previdenciário e civil — base para tudo de imposto, ICMS, IRPF, CVM, regulação BR.",
        tags=["legal", "tributario", "br", "pt", "fiscal", "imposto"],
        search_url_template="/busca?q={query}",
    ),
    Site(
        "gov.uk",
        category="UK government services",
        description="Official UK government — tax (HMRC), VAT, business, benefits, residency, regulations, public services.",
        tags=["gov", "tax", "uk", "hmrc", "vat", "en"],
        search_url_template="/search/all?keywords={query}",
    ),
    Site(
        "agenciatributaria.es",
        category="Hacienda España (impuestos)",
        description="Agencia Tributaria de España — IRPF, IVA, declaración renta, modelo 303, autónomos, sociedades, criptomonedas.",
        tags=["tax", "es", "hacienda", "irpf", "iva", "tributario"],
        search_url_template="/AEAT.search?p_q={query}",
    ),
    Site(
        "britannica.com",
        category="general encyclopedia (English)",
        description="Encyclopædia Britannica — general knowledge, history, science, biography, geography, arts.",
        tags=["encyclopedia", "general", "knowledge", "en"],
        search_url_template="/search?query={query}",
    ),
    Site(
        "folha.uol.com.br",
        category="jornal brasileiro Folha de São Paulo",
        description="Jornal Folha — notícias gerais Brasil e mundo: política, economia, cultura, esporte, ciência, opinião.",
        tags=["news", "br", "pt", "jornal"],
        search_url_template="/busca/?q={query}",
    ),
    Site(
        "elpais.com",
        category="periódico El País España",
        description="El País — periódico español, noticias generales: política, economía, cultura, deportes, ciencia.",
        tags=["news", "es", "espanol", "periodico"],
        search_url_template="/buscador/?q={query}",
    ),
]

# ---- Queries ---------------------------------------------------------------

PT_TAX = [
    "imposto de renda pessoa física 2026 declaração",
    "tabela ISS São Paulo serviços alíquota",
    "ICMS tributação interestadual diferencial",
    "MEI faturamento limite anual 2026",
    "Simples Nacional anexo III alíquota",
    "PIS COFINS regime cumulativo não cumulativo",
    "Lucro Real apuração trimestral pessoa jurídica",
    "IPTU isenção idoso aposentado",
    "ITBI valor venal município São Paulo",
    "IPVA tabela FIPE valor venal",
    "ISS retenção fonte tomador serviço",
    "DARF código pagamento receita federal",
    "Reforma Tributária IBS CBS implementação",
    "Receita Federal CPF regularização situação",
    "Lei Complementar 116 ISS lista serviços",
]

EN_TAX = [
    "IRS form 1040 individual income tax",
    "capital gains tax US 2026 long term",
    "tax deduction self employed home office",
    "estimated quarterly tax payment IRS",
    "401k contribution limit 2026",
    "FBAR foreign bank account reporting requirements",
    "tax credit child dependent deduction",
    "VAT registration UK threshold HMRC",
    "Roth IRA conversion tax implications",
    "1099 tax form independent contractor",
    "EIN application LLC IRS",
    "tax loss harvesting strategy ETF",
    "section 179 deduction equipment business",
    "alternative minimum tax AMT calculation",
    "stamp duty UK property tax 2026",
]

ES_TAX = [
    "declaración renta IRPF 2026 España",
    "modelo 303 IVA trimestral autónomo",
    "autónomo cuota Seguridad Social tarifa plana",
    "tributación criptomonedas España 2026",
    "deducción vivienda habitual hipoteca",
    "modelo 720 bienes extranjero declaración",
    "Hacienda devolución renta plazo 2026",
    "Impuesto Sociedades tipo general empresas",
    "IRPF retención nómina cálculo",
    "Patrimonio impuesto comunidades autónomas",
    "IVA reducido productos básicos alimentos",
    "régimen especial agricultura IVA módulos",
    "Impuesto Sucesiones donaciones autonómicas",
    "Plusvalía municipal Tribunal Constitucional",
    "tributación trabajador desplazado extranjero",
]

PT_GENERAL = [
    "história da República Velha Brasil",
    "biografia Machado de Assis escritor",
    "fórmula química água oxigenada uso",
    "como fazer feijoada tradicional receita",
    "treino academia hipertrofia muscular iniciante",
    "diabetes tipo 2 tratamento controle",
    "café especial torra grãos brasileiros",
    "carros elétricos brasileiros 2026 lançamentos",
    "literatura brasileira modernismo Mário Andrade",
    "anatomia coração humano câmaras",
    "evolução Darwin seleção natural espécies",
    "vinhos chilenos cabernet sauvignon Maipo",
    "futebol brasileiro Copa Libertadores 2026",
    "música samba origem história Rio",
    "energia solar painéis fotovoltaicos residencial",
]

EN_GENERAL = [
    "history of the Roman Empire fall",
    "Shakespeare Hamlet analysis themes",
    "DNA replication process biology",
    "Italian carbonara recipe traditional",
    "HIIT cardio workout routine beginner",
    "diabetes type 2 management diet",
    "espresso coffee extraction technique",
    "electric vehicle battery technology 2026",
    "Hemingway Old Man and the Sea",
    "human brain anatomy cortex regions",
    "evolution natural selection Darwin theory",
    "French wine Bordeaux region grapes",
    "Premier League standings 2026 season",
    "jazz history Louis Armstrong New Orleans",
    "solar panel efficiency 2026 technology",
]

ES_GENERAL = [
    "historia España Reconquista cronología",
    "Gabriel García Márquez novelas Cien Años",
    "ADN replicación proceso biología molecular",
    "paella valenciana receta tradicional",
    "rutina entrenamiento gimnasio fuerza principiante",
    "diabetes tipo 2 tratamiento dieta",
    "café especial tueste Colombia origen",
    "vehículos eléctricos España 2026 modelos",
    "Cervantes Don Quijote análisis literario",
    "anatomía cerebro humano corteza",
    "evolución selección natural Darwin teoría",
    "vinos Rioja Tempranillo crianza",
    "fútbol La Liga clasificación 2026",
    "flamenco origen historia España Andalucía",
    "energía solar paneles fotovoltaicos España",
]

ALL_QUERIES = (
    [("PT-TAX", q) for q in PT_TAX]
    + [("EN-TAX", q) for q in EN_TAX]
    + [("ES-TAX", q) for q in ES_TAX]
    + [("PT-GEN", q) for q in PT_GENERAL]
    + [("EN-GEN", q) for q in EN_GENERAL]
    + [("ES-GEN", q) for q in ES_GENERAL]
)


# ---- Run -------------------------------------------------------------------


def main():
    import os

    engine = SearchEngine(
        llm="ollama/qwen2.5:7b",
        router_strategy="llm",
        router_top_k=2,
        parallel_sites=2,
        cache_dir="./test-cache-90",
        auto_resolve_dns=True,
        auto_escalate_adapter=True,
    )
    for s in SITES:
        try:
            engine.add(s, replace=True)
        except Exception as e:  # noqa: BLE001
            print(f"could not add {s.url}: {e}")

    rows = []
    t_global = time.perf_counter()

    print(f"Running {len(ALL_QUERIES)} queries against {len(SITES)} sites...\n")

    for i, (label, query) in enumerate(ALL_QUERIES, 1):
        t0 = time.perf_counter()
        try:
            result = engine.search(query, depth=1, max_results=3, timeout=12.0)
        except Exception as e:  # noqa: BLE001
            elapsed = time.perf_counter() - t0
            print(f"[{i:>2}] {label} {elapsed:>4.1f}s ERROR: {type(e).__name__}: {e}")
            rows.append((i, label, query[:48], "", 0, "error", round(elapsed, 1), ""))
            continue
        elapsed = time.perf_counter() - t0
        routed = ", ".join(d.site for d in result.routing_decisions)
        first_title = result.chunks[0].title[:55] if result.chunks else "—"
        first_url = result.chunks[0].source_url if result.chunks else ""
        rows.append(
            (i, label, query[:48], routed, len(result.chunks), result.status, round(elapsed, 1), first_title)
        )
        sym = {"ok": "✓", "partial": "~", "blocked": "✗"}.get(result.status, "?")
        print(
            f"[{i:>2}] {label} {sym} {elapsed:>4.1f}s "
            f"chunks={len(result.chunks)} | route={routed} | first: {first_title}"
        )

    total = time.perf_counter() - t_global
    print("\n" + "=" * 90)
    print(
        f"DONE in {total/60:.1f} min  |  total tokens: {engine._llm.tokens}"
        f"  |  cost: ${engine._llm.cost_usd:.4f}"
    )

    # ----- summaries -----
    by_lang = Counter(r[1] for r in rows)
    by_status = Counter(r[5] for r in rows)
    by_site = Counter()
    for r in rows:
        for s in r[3].split(", "):
            if s:
                by_site[s] += 1

    print()
    print("Status breakdown:")
    for status, n in by_status.most_common():
        pct = 100 * n / len(rows)
        print(f"  {status:<10} {n:>3}/{len(rows)}  ({pct:.0f}%)")

    def block(name: str, prefix: str):
        sub = [r for r in rows if r[1] == prefix]
        ok = sum(1 for r in sub if r[5] == "ok")
        partial = sum(1 for r in sub if r[5] == "partial")
        blocked = sum(1 for r in sub if r[5] == "blocked")
        nchunks = sum(r[4] for r in sub) / max(len(sub), 1)
        avg_t = sum(r[6] for r in sub) / max(len(sub), 1)
        print(f"  {name:<8} ok={ok:>2} partial={partial:>2} blocked={blocked:>2}"
              f"  | mean {avg_t:.1f}s, {nchunks:.1f} chunks/q")

    print()
    print("Per-language / per-category:")
    for grp in ["PT-TAX", "EN-TAX", "ES-TAX", "PT-GEN", "EN-GEN", "ES-GEN"]:
        block(grp, grp)

    print()
    print("Site routing distribution (top 10):")
    for site, n in by_site.most_common(10):
        print(f"  {site:<25} picked {n:>3}x")

    print()
    print("Selector cache (sites the LLM extracted patterns for):")
    for k, v in engine.cache_stats().items():
        print(f"  {k:<25} hits={v.get('hits', 0)} fails={v.get('fails', 0)}")

    # save full table
    import json

    with open("./test-cache-90/results.json", "w", encoding="utf-8") as f:
        json.dump([
            dict(zip(["i", "label", "query", "routed", "chunks", "status", "secs", "first"], r))
            for r in rows
        ], f, ensure_ascii=False, indent=2)
    print("\nFull table written to ./test-cache-90/results.json")


if __name__ == "__main__":
    main()
