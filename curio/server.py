"""FastAPI dashboard for catalog management, search, and cache inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .catalog import Catalog, Site
from .engine import SearchEngine

try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel
except ImportError as e:  # pragma: no cover
    raise ImportError("Dashboard requires extras: pip install 'curio[server]'") from e


_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>curio dashboard</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           margin: 2rem auto; max-width: 960px; color:#1e1e1e; padding: 0 1rem; }
    h1 { margin-top: 0; font-weight: 600; }
    code, pre { background: #f5f5f5; padding: 0.1rem 0.3rem; border-radius: 4px; }
    .row { display:flex; gap: .5rem; margin-bottom: 1rem; }
    input, button, textarea { font: inherit; padding: .5rem .75rem; border: 1px solid #ccc; border-radius: 6px; }
    button { background:#222; color:#fff; cursor:pointer; }
    table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
    th, td { text-align:left; padding: .35rem .5rem; border-bottom: 1px solid #eee; vertical-align: top; }
    th { color:#666; font-weight: 500; }
    .small { color:#777; font-size: .85em; }
    .status-blocked { color:#b00; }
    .status-partial { color:#b88500; }
    pre { white-space: pre-wrap; font-size: .85em; }
  </style>
</head>
<body>
  <h1>curio</h1>
  <p class="small">Curated AI search for agents — manage your catalog, run searches, peek at the cache.</p>

  <h2>Search</h2>
  <div class="row">
    <input id="q" style="flex:1" placeholder="query…">
    <input id="depth" type="number" value="1" min="0" max="3" style="width: 4rem">
    <button onclick="runSearch()">Search</button>
  </div>
  <div id="results"></div>

  <h2>Catalog</h2>
  <div class="row">
    <input id="newUrl" placeholder="cvm.gov.br" style="flex:1">
    <input id="newCategory" placeholder="category">
    <input id="newTags" placeholder="tags,comma">
    <button onclick="addSite()">Add</button>
  </div>
  <div id="catalog"></div>

  <script>
    async function loadCatalog() {
      const res = await fetch('/api/sites');
      const sites = await res.json();
      const t = document.getElementById('catalog');
      t.innerHTML = '<table><thead><tr><th>URL</th><th>Category</th><th>Tags</th><th>Behavior</th><th></th></tr></thead><tbody>'
        + sites.map(s => `<tr><td>${s.url}</td><td>${s.category||''}</td><td>${(s.tags||[]).join(', ')}</td><td>${s.behavior}</td><td><button onclick="rm('${s.url}')">×</button></td></tr>`).join('')
        + '</tbody></table>';
    }
    async function addSite() {
      const url = document.getElementById('newUrl').value.trim();
      if (!url) return;
      const body = {
        url,
        category: document.getElementById('newCategory').value.trim() || null,
        tags: document.getElementById('newTags').value.split(',').map(s=>s.trim()).filter(Boolean),
      };
      await fetch('/api/sites', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify(body)});
      ['newUrl','newCategory','newTags'].forEach(id => document.getElementById(id).value = '');
      loadCatalog();
    }
    async function rm(url) {
      await fetch('/api/sites/' + encodeURIComponent(url), {method:'DELETE'});
      loadCatalog();
    }
    async function runSearch() {
      const q = document.getElementById('q').value.trim();
      const depth = +document.getElementById('depth').value;
      if (!q) return;
      const r = document.getElementById('results');
      r.innerHTML = '<p class="small">searching…</p>';
      const res = await fetch('/api/search?q=' + encodeURIComponent(q) + '&depth=' + depth);
      const data = await res.json();
      r.innerHTML =
        `<p class="small">${data.chunks.length} results · ${data.duration_ms.toFixed(0)} ms · $${data.cost_estimate_usd.toFixed(4)} <span class="status-${data.status}">[${data.status}]</span></p>`
        + '<table><thead><tr><th>#</th><th>Site</th><th>Title</th><th>Score</th></tr></thead><tbody>'
        + data.chunks.map((c,i)=>`<tr><td>${i+1}</td><td>${c.site}</td><td><a href="${c.source_url}" target="_blank">${c.title}</a><br><span class="small">${(c.snippet||'').slice(0,200)}</span></td><td>${c.relevance_score.toFixed(2)}</td></tr>`).join('')
        + '</tbody></table>';
    }
    loadCatalog();
  </script>
</body>
</html>
"""


class _SiteIn(BaseModel):
    url: str
    category: str | None = None
    description: str | None = None
    tags: list[str] = []
    behavior: str = "natural"


def build_app(*, catalog_path: Path | None = None) -> FastAPI:
    """Construct the dashboard FastAPI app."""
    cache_dir = Path("~/.curio").expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)

    catalog = Catalog(catalog_path or cache_dir / "catalog.db")
    engine: SearchEngine | None = None

    def _engine() -> SearchEngine:
        nonlocal engine
        if engine is None:
            engine = SearchEngine(catalog=catalog)
        return engine

    app = FastAPI(title="curio dashboard", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _INDEX_HTML

    @app.get("/api/sites")
    def list_sites() -> list[dict[str, Any]]:
        return catalog.to_dicts()

    @app.post("/api/sites")
    def add_site(payload: _SiteIn) -> dict[str, Any]:
        site = Site(**payload.model_dump())
        catalog.add(site, replace=True)
        return {"ok": True, "url": site.url}

    @app.delete("/api/sites/{url:path}")
    def remove_site(url: str):
        if not catalog.remove(url):
            raise HTTPException(404, "site not found")
        return {"ok": True}

    @app.get("/api/cache")
    def cache_stats():
        return _engine().cache_stats()

    @app.get("/api/search")
    def do_search(
        q: str = Query(...),
        depth: int = Query(1, ge=0, le=3),
        max_results: int = Query(10, ge=1, le=50),
    ):
        result = _engine().search(q, depth=depth, max_results=max_results)
        return result.model_dump()

    return app


__all__ = ["build_app"]
