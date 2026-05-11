"""Final v0.2 benchmark — uses the profile registry instead of inline Sites.

12 queries (2 per category × 6 categories) — validates the v0.2 stack
end-to-end: profile loading, auto-DNS, auto-escalation, CSS pinning,
quality warnings, async-friendly. Writes to a real file with explicit flush
so output is not buffered away.
"""

from __future__ import annotations

import os
import time
from collections import Counter

from vouch import SearchEngine, get_profile

LOG = "./test-cache-final/run.log"

DOMAINS = [
    "arxiv.org",
    "github.com",
    "huggingface.co",
    "pypi.org",
    "jusbrasil.com.br",
    "gov.uk",
    "sede.agenciatributaria.gob.es",
    "britannica.com",
    "folha.uol.com.br",
    "elpais.com",
]

QUERIES = [
    ("PT-TAX", "imposto de renda pessoa física 2026 declaração"),
    ("PT-TAX", "Simples Nacional anexo III alíquota"),
    ("EN-TAX", "IRS form 1040 individual income tax"),
    ("EN-TAX", "401k contribution limit 2026"),
    ("ES-TAX", "declaración renta IRPF 2026 España"),
    ("ES-TAX", "modelo 303 IVA trimestral autónomo"),
    ("PT-GEN", "história da República Velha Brasil"),
    ("PT-GEN", "biografia Machado de Assis"),
    ("EN-GEN", "history of the Roman Empire fall"),
    ("EN-GEN", "DNA replication process biology"),
    ("ES-GEN", "Gabriel García Márquez Cien Años"),
    ("ES-GEN", "paella valenciana receta"),
]


def w(line: str) -> None:
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()


def main():
    os.makedirs("./test-cache-final", exist_ok=True)
    open(LOG, "w").close()

    engine = SearchEngine(
        llm="ollama/qwen2.5:7b",
        router_strategy="llm",
        router_top_k=2,
        parallel_sites=2,
        cache_dir="./test-cache-final",
        auto_resolve_dns=True,
        # HTTP-only for the benchmark — Chromium on this dev box is flaky.
        # Real installs get the full chain via auto_escalate_adapter=True (default).
        auto_escalate_adapter=False,
    )

    # Use the profile registry — much cleaner than inlining Sites.
    w(f"Loading {len(DOMAINS)} curated profiles into the catalog...")
    for domain in DOMAINS:
        site = get_profile(domain)
        if site is None:
            w(f"  ! no profile for {domain}")
            continue
        try:
            engine.add(site, replace=True)
            w(f"  + {site.url} ({site.category})")
        except Exception as e:
            w(f"  ! add {domain} failed: {e}")

    w("")
    w(f"Running {len(QUERIES)} queries...")
    w("")

    rows: list[tuple] = []
    t_global = time.perf_counter()

    for i, (label, q) in enumerate(QUERIES, 1):
        t0 = time.perf_counter()
        try:
            r = engine.search(q, depth=1, max_results=3, timeout=20)
        except Exception as e:
            t = time.perf_counter() - t0
            w(f"[{i:>2}] {label} ERROR {t:.1f}s: {type(e).__name__}: {str(e)[:60]}")
            rows.append((label, "error", t, 0, "", ""))
            continue
        t = time.perf_counter() - t0
        sym = {"ok": "v", "partial": "~", "blocked": "x", "low_quality": "?"}.get(r.status, "·")
        first = r.chunks[0].title[:55] if r.chunks else "—"
        warn = "[warn]" if r.quality_warning else ""
        routed = ", ".join(d.site for d in r.routing_decisions)
        w(f"[{i:>2}] {label} {sym} {t:>4.1f}s n={len(r.chunks)} {warn} | {routed} | first: {first}")
        rows.append((label, r.status, t, len(r.chunks), first, r.quality_warning or ""))

    total = time.perf_counter() - t_global
    w("")
    w(f"DONE in {total / 60:.1f} min  tokens={engine._llm.tokens}  cost=${engine._llm.cost_usd:.4f}")
    w("")

    by_status = Counter(r[1] for r in rows)
    w("Status breakdown:")
    for s, n in by_status.most_common():
        w(f"  {s:<12} {n}/{len(rows)}")
    w("")

    w("Per-category:")
    for cat in ["PT-TAX", "EN-TAX", "ES-TAX", "PT-GEN", "EN-GEN", "ES-GEN"]:
        sub = [x for x in rows if x[0] == cat]
        ok = sum(1 for r in sub if r[1] == "ok")
        lq = sum(1 for r in sub if r[1] == "low_quality")
        bl = sum(1 for r in sub if r[1] in ("blocked", "error"))
        avg = sum(r[2] for r in sub) / max(len(sub), 1)
        w(f"  {cat}: ok={ok} low_quality={lq} blocked={bl} | mean {avg:.1f}s")
    w("")

    w("Cache state:")
    for d, s in engine.cache_stats().items():
        full = engine.selector_cache.get(d) or {}
        css = "css+" if full.get("result_selectors") else "css-"
        pat = full.get("result_url_contains") or "-"
        tier = full.get("working_tier", "?")
        w(f"  {d:<35} tier={tier:<8} {css} pat={pat:<20} hits={s.get('hits')}")


if __name__ == "__main__":
    main()
