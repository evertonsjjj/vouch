# Changelog

All notable changes to **curio** are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project follows [Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-05-10

### Added

- **CSS selector pinning** — the result-extraction LLM now examines DOM context
  (ancestor tag chain, sibling tags, full HTML of one candidate card) and emits
  reusable CSS selector tuples (`container`, `title`, `url`, `snippet`, `date`,
  `author`). Subsequent calls replay via `lxml.cssselect` — deterministic,
  no LLM call. Cached in `selectors.db`.
- **Auto-escalation chain** — adapter ladder (`http` → `browser` → `stealth`).
  Each search records `working_tier` and `failed_tiers` per site; the next
  call starts at the cheapest tier known to work for that domain. When the
  current tier returns chunks but they look like nav/megamenu, the engine
  keeps escalating instead of accepting the junk.
- **Auto-DNS resolution** — `engine.add(Site("foo.es"), ...)` with
  `auto_resolve_dns=True` probes a short list of canonical hostname variants
  (`www.`, `sede.`, `agencia.`, `<root>.gob.es`, `<root>.gov.br`, …) and
  picks the one that responds. Fixes `agenciatributaria.es` →
  `sede.agenciatributaria.gob.es` automatically.
- **Smarter quality detector** — `looks_low_quality()` now flags megamenu
  patterns, recursive search-page links, "no results" / "nenhum resultado" /
  "no se encontraron" sentinels in HTML, and short categorical titles.
- **Probe crawl on add()** — opt-in `auto_probe_on_add=True` runs a tiny
  probe query the moment a site is added so the engine learns its
  working_tier and selectors before any real user query.
- **Profile registry** — bundled `curio/profiles/builtin.yaml` ships with
  curated profiles for 24 popular sites (arxiv, github, huggingface, pypi,
  npmjs, crates, MDN, Wikipedia ×3, gov.uk, irs.gov, sede.agenciatributaria,
  jusbrasil, planalto, BBC, Folha, El País, Stack Overflow, Reddit, …).
  New CLI commands: `curio profiles list/show/import`.
- **Accept-Language header** — query language detected (PT/ES/EN/FR/IT/DE)
  and matching `Accept-Language` is sent on HTTP fetches. Reduces redirects
  to wrong-language site versions.
- **Result formatting helpers** — `SearchResult.to_markdown()`,
  `to_json()`, `to_dict()` for clean rendering in chat / docs / files.
- **Async API** — `engine.asearch(query, ...)` returns a `SearchResult`
  awaitable, friendly for agent frameworks.
- **`SearchResult.quality_warning`** — populated when extracted chunks pass
  the heuristic but `looks_low_quality()` flags them, so callers know
  *something* but it's probably nav/shell.
- **Browser stability on Windows** — process-wide
  `threading.Semaphore(_MAX_PARALLEL_BROWSERS=1)` gates concurrent Chromium
  launches; cleanup is now exception-safe.
- **57 unit tests** covering catalog, router, engine, cache, extraction,
  CSS selectors, quality detector, language detection, DNS resolver, models.

### Changed

- `Site.__init__` now accepts a positional URL (`Site("cvm.gov.br")`),
  matching the README's documented API.
- `build_adapter` prefers `HTTPAdapter` whenever a `search_url_template` is
  set (10× faster) — falls back to `BrowserAdapter` otherwise.
- `BrowserAdapter` waits for `networkidle` after `domcontentloaded` so
  XHR-rendered results pages are captured.
- `_adapter_ladder` skips the `stealth` tier automatically when `patchright`
  isn't installed — avoids re-running the plain BrowserAdapter twice.
- Heuristic extractor's host filter is now subdomain-aware
  (`developer.mozilla.org` rejects links to `www.mozilla.org`).
- Selector cache is always truthy (`__bool__ → True`); fixes a fresh-cache
  bug where `if self.cache and selectors:` evaluated False on empty cache.

### Bug fixes

- CLI `--version` no longer requires a subcommand to short-circuit.
- `to_chunks` (HTTPAdapter path) now calls the same nav-anchor filter as
  the BrowserAdapter path; `_split_into_result_chunks` removed.

## [0.1.0] — initial release

- Three-level API (one-shot `search()`, `SearchEngine`, YAML catalog).
- Sync engine, parallel-site fetcher, LLM router with strategies
  (`llm`, `embedding`, `tags`, `all`).
- HTTP and Browser (Playwright) adapters; Patchright stealth optional.
- LLM-powered search-bar discovery + selector cache.
- LLM result-extraction fallback with URL-pattern cache.
- Catalog (SQLite) + Site model.
- CLI (`search`, `catalog`, `serve`, `mcp`).
- FastAPI dashboard.
- CrewAI / LangChain / PydanticAI / MCP integrations.
- Optional vision-LLM CAPTCHA solver, APScheduler change monitor.

[0.2.0]: https://github.com/yourhandle/curio/releases/tag/v0.2.0
[0.1.0]: https://github.com/yourhandle/curio/releases/tag/v0.1.0
