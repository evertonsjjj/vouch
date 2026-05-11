"""18-query final benchmark (3 per category) — synchronous, definitive run."""

from __future__ import annotations

import os
import sys
import time
from collections import Counter

# Force unbuffered + UTF-8
os.environ["PYTHONUNBUFFERED"] = "1"

from vouch import SearchEngine, Site

LOG = "./test-cache-18/run.log"

SITES = [
    Site("arxiv.org", category="academic ML/AI papers",
         description="Preprints in CS, ML, AI, math.",
         tags=["research", "ml", "ai"],
         search_url_template="/search/?searchtype=all&query={query}"),
    Site("github.com", category="open-source code",
         description="Repos, libraries, frameworks.",
         tags=["code", "dev"],
         search_url_template="/search?q={query}&type=repositories"),
    Site("huggingface.co", category="ML models",
         description="ML models, datasets.",
         tags=["ml", "models"],
         search_url_template="/models?search={query}"),
    Site("pypi.org", category="Python packages",
         description="Python package index.",
         tags=["python", "dev"],
         search_url_template="/search/?q={query}"),
    Site("jusbrasil.com.br", category="legislação BR",
         description="Conteúdo jurídico, leis, tributário, fiscal.",
         tags=["legal", "tributario", "br"],
         search_url_template="/busca?q={query}"),
    Site("gov.uk", category="UK government",
         description="HMRC, VAT, business, tax UK.",
         tags=["gov", "tax", "uk"],
         search_url_template="/search/all?keywords={query}"),
    Site("agenciatributaria.es", category="Hacienda España",
         description="Agencia Tributaria — IRPF, IVA.",
         tags=["tax", "es"],
         search_url_template="/AEAT.search?p_q={query}"),
    Site("britannica.com", category="enciclopédia",
         description="Encyclopædia Britannica.",
         tags=["encyclopedia"],
         search_url_template="/search?query={query}"),
    Site("folha.uol.com.br", category="jornal BR",
         description="Folha — notícias.",
         tags=["news", "br"],
         search_url_template="/busca/?q={query}"),
    Site("elpais.com", category="periódico ES",
         description="El País — noticias.",
         tags=["news", "es"],
         search_url_template="/buscador/?q={query}"),
]

QUERIES = [
    ("PT-TAX", "imposto de renda pessoa física 2026 declaração"),
    ("PT-TAX", "MEI faturamento limite anual 2026"),
    ("PT-TAX", "Simples Nacional anexo III alíquota"),
    ("EN-TAX", "IRS form 1040 individual income tax"),
    ("EN-TAX", "401k contribution limit 2026"),
    ("EN-TAX", "tax deduction self employed home office"),
    ("ES-TAX", "declaración renta IRPF 2026 España"),
    ("ES-TAX", "modelo 303 IVA trimestral autónomo"),
    ("ES-TAX", "tributación criptomonedas España 2026"),
    ("PT-GEN", "história da República Velha Brasil"),
    ("PT-GEN", "biografia Machado de Assis escritor"),
    ("PT-GEN", "como fazer feijoada tradicional receita"),
    ("EN-GEN", "history of the Roman Empire fall"),
    ("EN-GEN", "DNA replication process biology"),
    ("EN-GEN", "Italian carbonara recipe traditional"),
    ("ES-GEN", "Gabriel García Márquez novelas Cien Años"),
    ("ES-GEN", "paella valenciana receta tradicional"),
    ("ES-GEN", "historia España Reconquista cronología"),
]


def w(line):
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()


def main():
    os.makedirs("./test-cache-18", exist_ok=True)
    open(LOG, "w").close()

    engine = SearchEngine(
        llm="ollama/qwen2.5:7b",
        router_strategy="llm",
        router_top_k=2,
        parallel_sites=2,
        cache_dir="./test-cache-18",
        auto_resolve_dns=True,
        auto_escalate_adapter=True,
    )
    for s in SITES:
        try:
            engine.add(s, replace=True)
        except Exception as e:
            w(f"add {s.url} failed: {e}")

    t_global = time.perf_counter()
    rows = []
    w(f"Running {len(QUERIES)} queries against {len(SITES)} sites")
    w("")

    for i, (label, q) in enumerate(QUERIES, 1):
        t0 = time.perf_counter()
        try:
            r = engine.search(q, depth=1, max_results=3, timeout=20)
        except Exception as e:
            t = time.perf_counter() - t0
            w(f"[{i:>2}] {label} ERROR {t:.1f}s: {type(e).__name__}: {str(e)[:60]}")
            rows.append((label, "error", t, 0, ""))
            continue
        t = time.perf_counter() - t0
        sym = {"ok": "v", "partial": "~", "blocked": "x"}.get(r.status, "?")
        first = r.chunks[0].title[:55] if r.chunks else "-"
        routed = ", ".join(d.site for d in r.routing_decisions)
        w(f"[{i:>2}] {label} {sym} {t:>4.1f}s n={len(r.chunks)} | {routed} | first: {first}")
        rows.append((label, r.status, t, len(r.chunks), first))

    total = time.perf_counter() - t_global
    w("")
    w(f"DONE in {total/60:.1f} min  tokens={engine._llm.tokens}")
    w("")
    by = Counter(r[1] for r in rows)
    w(f"Status: ok={by['ok']} partial={by['partial']} blocked={by['blocked']} error={by['error']}")
    w("")
    for cat in ["PT-TAX","EN-TAX","ES-TAX","PT-GEN","EN-GEN","ES-GEN"]:
        sub = [r for r in rows if r[0]==cat]
        ok = sum(1 for r in sub if r[1]=="ok")
        w(f"  {cat}: {ok}/{len(sub)} ok | {sum(r[2] for r in sub)/max(len(sub),1):.1f}s avg")
    w("")
    w("Cache:")
    for d, s in engine.cache_stats().items():
        full = engine.selector_cache.get(d) or {}
        css = "css+" if full.get("result_selectors") else "css-"
        pat = full.get("result_url_contains") or "-"
        w(f"  {d:<35} tier={full.get('working_tier','?'):<8} {css} pat={pat}")


if __name__ == "__main__":
    main()
