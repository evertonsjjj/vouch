# Changelog

All notable changes to **vouch** are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project follows [Semantic Versioning](https://semver.org/).

## [0.2.3] — 2026-05-11

Two more residuals from the curio → vouch rename.

### Fixed

- ``LICENSE``: copyright header said "curio contributors". Now reads
  "vouch contributors", matching ``pyproject.toml``.
- ``.gitignore``: the runtime-data block was ignoring ``.curio/``. The
  actual runtime dir is ``~/.vouch`` (per ``cli.py``, ``config.py``,
  ``server.py``, ``profiles/update.py``); now ignores ``.vouch/``.

## [0.2.2] — 2026-05-11

Doc-only patch. No code changes; same wheel contents as 0.2.1 plus the
README fixes below.

### Documentation

- Fix ``YOURUSER`` placeholder in the Contributing snippet — now points
  at the real ``evertonsjjj/vouch`` clone URL.
- Rewrite the Roadmap section. The previous version listed change
  monitoring, FastAPI dashboard, and stealth mode under "v0.3" as if they
  were upcoming, but all three actually shipped in v0.2. New structure
  separates "Shipped" (with a pointer to CHANGELOG for detail) from
  "Coming next" (genuinely forward-looking items only).

## [0.2.1] — 2026-05-11

Pre-launch consistency pass. No behavior changes; all updates are documentation
accuracy, type-checking hygiene, and a soft method rename with a back-compat
alias. Safe upgrade from 0.2.0.

### Deprecated

- ``Catalog.list()`` and ``SearchEngine.list()`` renamed to ``list_sites()``.
  The old names still work as aliases through v0.x. The rename avoids shadowing
  the ``list`` builtin in class-scope type annotations (broke strict mypy).
  Will be removed in v1.0.
- ``CurioSearchTool`` (in ``vouch.integrations.crewai`` and
  ``vouch.integrations.langchain``) renamed to ``VouchSearchTool`` with the
  old name kept as an alias. Same v1.0 removal timeline as ``CurioError``.

### Documentation

- Removed unimplemented humanize claims from the README ("Bezier-curve mouse
  movement", "User-agent rotation"). The code never had either; replaced with
  what the ``humanize`` module actually does (lognormal pauses, typo injection,
  business-hours gating, single per-session UA).
- Install snippet split out ``[mcp]`` and ``[ocr]`` as separate extras; the
  ``[server]`` extra no longer claims to include the MCP server.
- ``[all]`` documented as "everything above" — framework integrations
  (``[crewai]`` / ``[langchain]`` / ``[pydantic-ai]``) ship as separate extras
  to avoid pulling in heavy dep trees by default.
- ``[vision]`` clarified as "image handling" (Pillow); the vision LLM itself
  comes from LiteLLM (already in core deps).
- Module-layout tree filled out (was missing ~12 files: models, config,
  exceptions, dns_resolver, plugins, browser_pool, probe, css_selectors,
  llm_extract, profiles/*, captcha/*, monitor/*).
- "Real numbers from internal benchmarks" softened with caveats; pointer to
  reproducible scripts in ``examples/``.
- Test count corrected (57 → 117).
- README acknowledgments reframed away from "portfolio project" toward
  "early-stage open source looking for contributors".
- Clarified that ``vouch profiles update`` requires internet and falls back
  to bundled profiles on any network failure.

### Internal

- ``mypy vouch/`` now passes cleanly (0 errors, down from 59).
  - Counter type annotation in ``_lang.py``.
  - ``catalog._hooks`` typed as ``dict[str, dict[str, Callable | None]]``.
  - ``_template_path`` asserts the caller-side invariant for ``search_url_template``.
  - One-shot ``search(sites=...)`` accepts ``Sequence[str | Site]`` (was
    invariant ``list[str | Site]``).
  - Two SQLAlchemy ``Column[datetime]`` assignment lines suppressed with
    targeted ``# type: ignore[assignment]``.
  - Dead ``TypeError`` fallback in ``plugins._load`` dropped — the only
    supported Python (3.10+) doesn't reach it.
- ``warn_unused_ignores`` set to ``false`` in the mypy config since optional
  integration imports legitimately need ``# type: ignore`` in environments
  that lack the extra.
- ``types-PyYAML`` added to dev deps.

## [0.2.0] — 2026-05-10

### Renamed

- **Package renamed from ``curio`` to ``vouch``** to avoid conflict with the
  existing ``curio`` async library on PyPI. The old ``CurioError`` exception
  is kept as a back-compat alias of ``VouchError`` and will be removed in
  v1.0. Update your imports::

      # before
      from curio import SearchEngine
      # after
      from vouch import SearchEngine

### Added

- **Browser pool** — one long-lived Chromium process per engine, shared
  across every search. Eliminates the per-call launch overhead (~3-8 s warm,
  worse cold) and the Windows stability issues from forking many Chromium
  instances. Opt-in via ``use_browser_pool=True`` (default on); set False to
  fall back to the v0.1 "fresh browser per search" path. Engine adds
  ``close()`` / context-manager protocol for explicit teardown.
- **Plugin model via entry_points** — three discovery groups:
    - ``vouch.adapters`` — per-host SiteAdapter implementations
      (``arxiv.org`` exact, ``*.gov.br`` suffix, or ``*`` fallback).
    - ``vouch.routers`` — alternative router strategies.
    - ``vouch.profiles`` — community ProfileRegistry bundles.
  Third parties can ``pip install vouch-adapter-arxiv`` and the next
  ``SearchEngine`` picks it up. See ``docs/plugins.md`` for the contract.
  CLI: ``vouch plugins list``.
- **Profile auto-update** — ``vouch profiles update`` fetches the latest
  community registry from a configurable URL (default
  ``github.com/evertonsjjj/vouch-profiles``), validates the YAML, and merges
  it on top of the bundled ``builtin.yaml``. Honors HTTP caching
  (ETag / If-Modified-Since) and falls back gracefully to the bundled
  profiles on any network failure.
- **Tesseract OCR fallback** for text CAPTCHAs (``vouch[ocr]``). Classical
  CPU OCR — ~50-200 ms per image, $0, no GPU, no model download. The
  ``CaptchaSolver`` now chains automatically: Tesseract first → vision LLM
  on low confidence → return best result. Image-grid CAPTCHAs still need a
  vision LLM (``ollama/qwen2.5vl:7b`` recommended). ``CaptchaResult`` gains
  a ``solver`` field showing which backend produced the answer.
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
- **Profile registry** — bundled `vouch/profiles/builtin.yaml` ships with
  curated profiles for 24 popular sites (arxiv, github, huggingface, pypi,
  npmjs, crates, MDN, Wikipedia ×3, gov.uk, irs.gov, sede.agenciatributaria,
  jusbrasil, planalto, BBC, Folha, El País, Stack Overflow, Reddit, …).
  New CLI commands: `vouch profiles list/show/import`.
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
- **117 unit tests** covering catalog, router, engine, cache, extraction,
  CSS selectors, quality detector, language detection, DNS resolver, models,
  CLI, profiles, plugins, async API, and integrations.

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

[0.2.3]: https://github.com/evertonsjjj/vouch/releases/tag/v0.2.3
[0.2.2]: https://github.com/evertonsjjj/vouch/releases/tag/v0.2.2
[0.2.1]: https://github.com/evertonsjjj/vouch/releases/tag/v0.2.1
[0.2.0]: https://github.com/evertonsjjj/vouch/releases/tag/v0.2.0
[0.1.0]: https://github.com/evertonsjjj/vouch/releases/tag/v0.1.0
