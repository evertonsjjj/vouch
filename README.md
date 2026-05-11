# vouch

> **Curated AI search for agents.** Bring your own sources, your own LLM. The self-hosted, agent-ready alternative to Tavily and Perplexity for trusted-source research.

[![PyPI version](https://img.shields.io/pypi/v/vouch)](https://pypi.org/project/vouch/)
[![CI](https://github.com/evertonsjjj/vouch/actions/workflows/ci.yml/badge.svg)](https://github.com/evertonsjjj/vouch/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**vouch** is a Python library that lets you register a list of trusted sites with metadata (category, description, tags), and then runs intelligent searches across them using any LLM — including local models via Ollama. The AI dynamically figures out *how* to search each site (no manual selectors), caches what it learns, and returns structured results ready to feed an agent.

```python
from vouch import SearchEngine, Site

engine = SearchEngine(llm="ollama/qwen2.5:14b")
engine.add(Site("cvm.gov.br", category="regulação financeira BR"))
engine.add(Site("arxiv.org", category="papers acadêmicos", tags=["ml", "ai"]))

results = engine.search("LLM agents in 2026", depth=2)
for r in results.chunks:
    print(f"[{r.source_url}] {r.title}\n{r.snippet}\n")
```

---

## Table of contents

- [Why vouch](#why-vouch)
- [How it compares](#how-it-compares)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Three ways to use](#three-ways-to-use)
- [Core concepts](#core-concepts)
- [The Site model](#the-site-model)
- [Search depth](#search-depth)
- [Smart Site Routing](#smart-site-routing)
- [Selector cache](#selector-cache)
- [Profile registry](#profile-registry)
- [LLM configuration (BYOK)](#llm-configuration-byok)
- [Using as an agent tool](#using-as-an-agent-tool)
- [Optional features](#optional-features)
- [Configuration reference](#configuration-reference)
- [Architecture](#architecture)
- [Cost and performance](#cost-and-performance)
- [Limits and what's out of scope](#limits-and-whats-out-of-scope)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [References and prior art](#references-and-prior-art)

---

## What's new in 0.2

- **CSS selector pinning** — the AI now examines DOM context and emits reusable `{container, title, url, snippet, date, author}` selectors. Cached in SQLite; subsequent calls replay via `lxml.cssselect` — no LLM, milliseconds.
- **Auto-escalation chain** — `http → browser → stealth`. The engine learns the cheapest tier each site needs and persists it.
- **Browser pool** — one shared Chromium across all searches in a session. Eliminates the per-call launch overhead and the Windows-on-fresh-fork instability.
- **Plugin model** — `pip install vouch-adapter-arxiv` (or anything matching `vouch-adapter-*`, `vouch-router-*`, `vouch-profiles-*`) and the next `SearchEngine` picks it up automatically via Python entry_points. See [`docs/plugins.md`](docs/plugins.md).
- **Profile registry + auto-update** — 24 curated profiles ship in the box (arxiv, github, huggingface, gov.uk, irs.gov, sede.agenciatributaria, jusbrasil, MDN, pypi, …). `vouch profiles update` pulls the latest community registry.
- **Auto-DNS resolution** — fixes wrong-host catalog entries automatically (`agenciatributaria.es` → `sede.agenciatributaria.gob.es`).
- **Async API** — `await engine.asearch(query, ...)` alongside the sync API.
- **Result formatting** — `result.to_markdown()`, `to_json()`.
- **Smarter quality detector** — flags megamenu shells, recursive search-page links, no-results sentinels in PT/ES/EN.
- **Probe crawl on `add()`** — opt-in: site profile is learned the moment you add it, not on the first user query.
- **Package renamed from `curio` to `vouch`** (the `curio` name on PyPI is taken by David Beazley's async library since 2016).

See [CHANGELOG.md](CHANGELOG.md) for the full list.

## Why vouch

The agentic AI ecosystem has two kinds of search tools:

- **Open-web search** (Tavily, Exa, Perplexica, Firecrawl `/search`): great for broad questions, but you can't tell them "only use these sources I trust."
- **Browser agents** (Stagehand, Skyvern, browser-use): great at navigating *one* site at a time, but they don't know *which* site to navigate to and don't keep a registry of your trusted sources.

**vouch fills the gap in between**: a persistent catalog of sites you trust, with an LLM that reads your descriptions to route each query to the right sources, a browser layer that learns how to search each site once and caches the selectors, and a clean tool interface for CrewAI / LangChain / PydanticAI / MCP.

It's what you'd build if you wanted Tavily, but **for your own list of sources**, **using your own LLM**, **without paying anyone**.

## How it compares

| | vouch | Tavily / Exa | Perplexica | browser-use | Stagehand | Kagi Lenses |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Curated source list with metadata | ✅ | ⚠️ per call | ❌ | ❌ | ❌ | ✅ |
| LLM routing by description | ✅ | ❌ | ❌ | ❌ | ❌ | ⚠️ |
| Dynamic search-bar discovery | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ |
| Cached selectors after first visit | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Adjustable depth (0–3) | ✅ | ⚠️ | ⚠️ | ❌ | ❌ | ❌ |
| BYOK + local LLM (Ollama) | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ |
| Self-hosted Python `pip install` | ✅ | ❌ | ❌ TS | ✅ | ⚠️ TS-first | ❌ |
| First-class agent tool | ✅ | ✅ | ❌ | ⚠️ | ⚠️ | ❌ |

## Installation

Minimal install (HTTP-only, no browser):

```bash
pip install vouch
```

Most users want the browser layer too:

```bash
pip install "vouch[browser]"
vouch install-browser   # downloads Chromium for Playwright
```

Optional extras:

```bash
pip install "vouch[browser,stealth]"     # patchright for harder sites
pip install "vouch[browser,ocr]"         # Tesseract CAPTCHA tier (CPU, no GPU)
pip install "vouch[browser,vision]"      # image handling for vision-LLM CAPTCHA
pip install "vouch[browser,monitor]"     # APScheduler for change tracking
pip install "vouch[browser,server]"      # FastAPI dashboard
pip install "vouch[mcp]"                 # MCP server (Claude Desktop, Cursor)
pip install "vouch[all]"                 # everything above
pip install "vouch[crewai]"              # framework integrations (separate)
pip install "vouch[langchain]"
pip install "vouch[pydantic-ai]"
```

**Requirements:** Python 3.10+. Linux, macOS, or Windows. ~500MB disk after `install-browser`.

## Quick start

### 30 seconds with Ollama

```bash
# 1. Make sure Ollama is running with a capable model
ollama pull qwen2.5:14b

# 2. Install vouch
pip install "vouch[browser]"
vouch install-browser

# 3. One-liner search
python -c "from vouch import search; print(search('arxiv attention transformers', sites=['arxiv.org']))"
```

### 30 seconds with a paid API

```bash
export ANTHROPIC_API_KEY=sk-ant-...
pip install "vouch[browser]"
vouch install-browser

python -c "from vouch import search; print(search('FDA drug approvals 2025', sites=['fda.gov'], llm='anthropic/claude-haiku-4-5'))"
```

## Three ways to use

vouch has **three progressive levels of API**. Pick the one that fits your case — they all coexist and use the same engine underneath.

### Level 1 — One-shot function

For quick scripts or trying it out:

```python
from vouch import search

results = search(
    query="regulamentação fundos 2026",
    sites=["cvm.gov.br", "valor.globo.com"],
    llm="ollama/qwen2.5:14b",
    depth=1,
)
```

No catalog, no metadata, no persistence. Ephemeral. Good for `python -c "..."`.

### Level 2 — Programmatic catalog

The typical workflow. Build a catalog in code:

```python
from vouch import SearchEngine, Site

engine = SearchEngine(
    llm="ollama/qwen2.5:14b",
    cache_dir="~/.vouch",   # selectors and metadata persist here
)

engine.add(Site(
    url="cvm.gov.br",
    category="regulação financeira BR",
    description="Comissão de Valores Mobiliários — regulamentos, deliberações, consultas públicas",
    tags=["gov", "financeiro", "regulação"],
))

engine.add(Site(
    url="arxiv.org",
    category="papers acadêmicos",
    description="Preprints em CS, math, physics, biology",
    tags=["research", "ml", "ai"],
))

# All metadata fields are optional. The LLM router uses whatever is provided.
engine.add(Site("news.ycombinator.com"))

# Search with automatic routing
results = engine.search("transformer architectures", depth=2)
```

The catalog persists in SQLite (`~/.vouch/catalog.db`). You can `engine.list_sites()`, `engine.remove("arxiv.org")`, `engine.update("arxiv.org", tags=[...])`. (`engine.list()` still works as a deprecated alias through v0.x.)

### Level 3 — YAML-declared catalog

For projects you want to version-control and share:

```yaml
# sites.yaml
defaults:
  llm: ollama/qwen2.5:14b
  depth: 1
  humanize: true

sites:
  - url: cvm.gov.br
    category: regulação financeira BR
    description: Comissão de Valores Mobiliários
    tags: [gov, financeiro]

  - url: arxiv.org
    category: papers acadêmicos
    description: Preprints em CS, math, physics
    tags: [research, ml, ai]

  - url: news.ycombinator.com
    # no metadata — that's fine, LLM will infer from URL

  - url: site-protegido.com
    behavior: stealth          # use patchright for this site
    rate_limit: "1/30s"        # be extra polite
```

```python
from vouch import SearchEngine

engine = SearchEngine.from_yaml("sites.yaml")
results = engine.search("LLM regulation")
```

Same engine, same SQLite cache, just a different way to declare the catalog. Good for CI, sharing with teammates, or templating per-project.

## Core concepts

vouch is built around four primitives. Understanding them helps you customize what you need:

```
┌──────────────────────────────────────────────────────────────┐
│                     SearchEngine                             │
│   the orchestrator — you mostly talk to this                 │
└──────────────────────────────────────────────────────────────┘
        │
        ├─── Catalog ──────── persistent registry of Sites
        │
        ├─── Router ────────── picks relevant Sites for a query
        │                      (uses Site metadata + LLM)
        │
        ├─── SiteAdapter ───── per-site search executor
        │     ├─ discovers selectors (LLM, first time)
        │     ├─ caches selectors (SQLite, every time after)
        │     └─ executes search + extraction
        │
        └─── Aggregator ────── ranks, dedups, returns SearchResult
```

Each is a `Protocol` — you can replace any of them. Want a custom router that uses a vector DB instead of LLM? Implement `Router`. Want to plug a paid scraping service? Implement `SiteAdapter`.

## The Site model

```python
from vouch import Site

Site(
    url: str,                       # required: "cvm.gov.br" or "https://cvm.gov.br"
    category: str | None = None,    # optional: "regulação financeira"
    description: str | None = None, # optional: free-text, fed to router LLM
    tags: list[str] | None = None,  # optional: ["gov", "financeiro"]
    
    # Behavioral overrides (all optional)
    behavior: str = "natural",      # "natural" | "stealth" | "external"
    rate_limit: str | None = None,  # "10/min", "1/30s", etc
    requires_login: bool = False,   # tells engine to handle auth flow
    search_url_template: str | None = None,  # bypass discovery: "/search?q={query}"
    
    # Custom hooks (advanced)
    pre_search: Callable | None = None,
    post_extract: Callable | None = None,
)
```

### How the optional metadata is used

- **Category and description** are concatenated and fed to the **router LLM** when there are too many sites to search them all. The LLM reads your descriptions and picks the most relevant subset for the query. With no description, the router falls back to the URL and any cached info.
- **Tags** can be used as filters (`engine.search(query, only_tags=["ml"])`) and as routing hints.
- **Behavior** controls the browser strategy (see [Optional features](#optional-features)).
- **`search_url_template`** is the escape hatch: if you already know how the site's search works (`https://github.com/search?q={query}`), provide it and vouch skips discovery entirely.

## Search depth

The `depth` parameter is the central knob for cost vs. quality:

| Depth | Behavior | Latency | Cost (typical) |
|---|---|---|---|
| **0** | Fetch homepage + extract recent content. No search interaction. | ~2s/site | ~$0 |
| **1** | Discover & execute search, return result snippets. | ~5–10s/site | $0.005–0.02 |
| **2** | Enter top-N results, extract full content. | ~20–40s/site | $0.05–0.15 |
| **3** | Follow internal links from results, deep crawl. | ~1–3min/site | $0.20–0.60 |

```python
# Quick check — just see what's on the homepages
engine.search("breaking news", depth=0)

# Standard — get search results
engine.search("LLM benchmarks", depth=1)

# Research mode — full content extraction
engine.search("GPT-5 architecture details", depth=2)

# Deep dive — agent navigates internal links
engine.search("complete history of CVM rule 175", depth=3)
```

Costs above assume Claude Haiku or Gemini Flash. With Ollama: $0 for everything except hardware/electricity.

## Smart Site Routing

When your catalog grows beyond ~5 sites, searching all of them for every query wastes time and tokens. vouch uses an LLM to **route**: given a query and your catalog metadata, pick the top-K most relevant sites.

```python
engine = SearchEngine(
    llm="ollama/qwen2.5:14b",
    router_top_k=3,                    # search top 3 sites per query
    router_strategy="llm",             # "llm" | "embedding" | "all" | "tags"
    router_explain=True,               # log why each site was chosen
)
```

### Strategies

- **`llm`** (default): single LLM call reads catalog + query, returns ranked sites. ~200 tokens, ~$0.0001 with Haiku, free with Ollama. Most accurate.
- **`embedding`**: pre-embeds catalog descriptions; routes via cosine similarity. ~10ms, no LLM call. Cheaper at scale, slightly less accurate. Uses `sentence-transformers` if installed.
- **`all`**: searches every site every time. Honest fallback for small catalogs (≤5).
- **`tags`**: filter by tag match. Useful when query domain is explicit.

```python
# Examples of router behavior
engine.search("Resolução CVM 175")
# → routes to: cvm.gov.br, valor.globo.com (skips arxiv, hacker news)

engine.search("attention is all you need paper")
# → routes to: arxiv.org (skips financial sites)

engine.search("python async best practices")
# → routes to: news.ycombinator.com (skips arxiv if no description match)
```

Inspect what the router did:

```python
results = engine.search("LLM eval methods")
print(results.routing_decisions)
# [
#   RouteDecision(site="arxiv.org", score=0.92, reason="academic ML papers"),
#   RouteDecision(site="news.ycombinator.com", score=0.61, reason="developer discussions"),
# ]
```

## Selector cache

The first time vouch visits a site, it spends an LLM call to figure out the search interface (where's the input? where's the submit? how do results render?). It caches what it learns in SQLite. **Subsequent searches on the same site use Playwright directly, with no LLM in the loop** — milliseconds, $0.

The cache is keyed by `(domain, dom_fingerprint)`. If the site redesigns and the cached selectors fail, vouch invalidates the entry and re-discovers automatically.

```python
# First search on cvm.gov.br: ~8s, $0.01 (LLM discovery)
# Second search on cvm.gov.br: ~2s, $0 (cached)
# After 1000 searches: still ~2s, still $0

engine.cache_stats()
# {
#   "cvm.gov.br": {"discovered": "2026-05-09", "hits": 47, "fails": 0},
#   "arxiv.org":  {"discovered": "2026-05-10", "hits": 12, "fails": 1},
# }

# Force re-discovery for a site
engine.invalidate_cache("cvm.gov.br")
```

The cache lives at `~/.vouch/selectors.db` — a tiny SQLite file you can ship in version control if you want a head-start for teammates.

## Profile registry

vouch ships with **curated profiles** for popular sites — preconfigured `Site` objects with the right `search_url_template`, tags, and category. You don't have to figure out arxiv's search URL or how to phrase HuggingFace's description.

```python
from vouch import SearchEngine, get_profile, list_profiles

engine = SearchEngine(llm="ollama/qwen2.5:14b")

# List what's bundled
list_profiles()
# → ['arxiv.org', 'bbc.com', 'crates.io', 'developer.mozilla.org',
#    'docs.python.org', 'elpais.com', 'en.wikipedia.org', 'es.wikipedia.org',
#    'folha.uol.com.br', 'github.com', 'gov.uk', 'huggingface.co', 'irs.gov',
#    'jusbrasil.com.br', 'news.ycombinator.com', 'npmjs.com',
#    'paperswithcode.com', 'pkg.go.dev', 'planalto.gov.br', 'pt.wikipedia.org',
#    'pypi.org', 'reddit.com', 'sede.agenciatributaria.gob.es',
#    'stackoverflow.com']

# Use a profile directly
engine.add(get_profile("arxiv.org"))
engine.add(get_profile("github.com"))
engine.add(get_profile("jusbrasil.com.br"))   # for BR legal/tax queries

results = engine.search("LLM benchmarks 2026")
```

Or via CLI:

```bash
vouch profiles list                      # show bundled profiles
vouch profiles show arxiv.org            # see one in detail
vouch profiles import arxiv.org,github.com,huggingface.co
vouch profiles import all                # add everything to your local catalog
```

The profile YAML lives at [`vouch/profiles/builtin.yaml`](vouch/profiles/builtin.yaml). Community contributions via PR welcome — see the [`new_profile`](.github/ISSUE_TEMPLATE/new_profile.md) issue template.

A separate community-maintained registry (`vouch-profiles` repo) is on the roadmap; teams can publish their domain-specific profiles there and run `vouch profiles update` to pull them.

## LLM configuration (BYOK)

vouch uses [LiteLLM](https://github.com/BerriAI/litellm) underneath, which means **any of 100+ providers** work with the same syntax.

### Local (Ollama, LM Studio)

Recommended models:
- **`ollama/qwen2.5:14b`** — best quality/size balance, runs in 16GB RAM
- **`ollama/qwen2.5:7b`** — faster, lower hardware
- **`ollama/qwen2.5-vl:7b`** — multimodal, needed for vision features
- **`ollama/llama3.2:8b`** — alternative

```python
engine = SearchEngine(llm="ollama/qwen2.5:14b")

# Or split: cheap model for routing, capable model for extraction
engine = SearchEngine(
    llm="ollama/qwen2.5:14b",          # discovery + extraction
    router_llm="ollama/qwen2.5:7b",    # routing decisions
)
```

### API providers

```python
# Anthropic
engine = SearchEngine(llm="anthropic/claude-haiku-4-5")
# requires ANTHROPIC_API_KEY env var

# OpenAI
engine = SearchEngine(llm="openai/gpt-4.1-mini")

# Google
engine = SearchEngine(llm="gemini/gemini-2.5-flash")

# Mix providers
engine = SearchEngine(
    llm="anthropic/claude-sonnet-4-6",
    router_llm="gemini/gemini-2.5-flash-lite",  # cheaper routing
    vision_llm="anthropic/claude-haiku-4-5",    # for CAPTCHA / visual extraction
)
```

### Pass keys explicitly

```python
engine = SearchEngine(
    llm="anthropic/claude-haiku-4-5",
    api_keys={
        "anthropic": "sk-ant-...",
        "openai": "sk-...",
    },
)
```

### Fallback chain

```python
engine = SearchEngine(
    llm=["anthropic/claude-haiku-4-5", "openai/gpt-4.1-mini", "ollama/qwen2.5:14b"],
)
# Tries each in order if previous fails
```

## Using as an agent tool

vouch's primary audience is agentic frameworks. First-class adapters:

### CrewAI

```python
from crewai import Agent, Task, Crew
from vouch.integrations.crewai import VouchSearchTool

search_tool = VouchSearchTool(catalog="sites.yaml", default_depth=2)

researcher = Agent(
    role="Financial Regulation Researcher",
    goal="Find recent CVM rules on fund management",
    tools=[search_tool],
    llm="anthropic/claude-sonnet-4-6",
)
```

### LangChain / LangGraph

```python
from langchain.agents import AgentExecutor
from vouch.integrations.langchain import VouchSearchTool

tools = [VouchSearchTool.from_yaml("sites.yaml")]
agent = AgentExecutor(tools=tools, ...)
```

### PydanticAI

```python
from pydantic_ai import Agent
from vouch.integrations.pydantic_ai import vouch_tool

agent = Agent("anthropic:claude-sonnet-4-6", tools=[vouch_tool("sites.yaml")])
```

### MCP server (Claude Desktop, Cursor, Cline)

```bash
vouch mcp serve --catalog sites.yaml
```

Configure in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "vouch": {
      "command": "vouch",
      "args": ["mcp", "serve", "--catalog", "/path/to/sites.yaml"]
    }
  }
}
```

Now Claude Desktop can call `search_curated_sources(query, depth)` directly.

## Optional features

### Human-like behavior

Reduces bot-detection signals on sites with simple behavioral analytics. **Does not bypass Cloudflare/DataDome/PerimeterX** — see [limits](#limits-and-whats-out-of-scope).

```python
engine = SearchEngine(
    llm="ollama/qwen2.5:14b",
    humanize=True,                    # default: lognormal pauses, variable typing speed
    typing_speed="natural",           # "fast" | "natural" | "slow"
    business_hours_only=False,        # restrict to user-local business hours
)
```

What it does:
- Lognormal pause distribution between actions (60–250ms typing, 0.5–3s reading)
- Random typo injection with backspace correction (~2% rate)
- Optional business-hours-only execution (`business_hours_only=True`)
- Single, recent Chrome user-agent applied per session (no rotation)

### Stealth mode (per site)

Drop-in [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) replacement for Playwright. Helps with mild Cloudflare Bot Fight Mode, fingerprint checks. **Does not defeat Turnstile invisible or DataDome.**

```python
engine.add(Site("portal-protegido.com", behavior="stealth"))
# OR globally:
engine = SearchEngine(default_behavior="stealth")
```

### CAPTCHA assist (lightweight by default)

Optional, opt-in, multi-backend. Two tiers used in order from cheapest to heaviest:

**1. Tesseract OCR** — for distorted-text CAPTCHAs (Receita, CVM, Jusbrasil, agencia tributaria, gov.uk).
CPU-only, ~50-200 ms per image, $0, no GPU, no model download.

```bash
pip install "vouch[ocr]"
# plus the system binary:
#   Ubuntu/Debian: sudo apt install tesseract-ocr tesseract-ocr-por tesseract-ocr-spa
#   macOS:         brew install tesseract tesseract-lang
#   Windows:       https://github.com/UB-Mannheim/tesseract/wiki
```

That's already enough for the common text-CAPTCHA case — no `vision_llm` needed.

**2. Vision LLM** — upgrade for image-grid CAPTCHAs ("select all traffic lights").

```python
engine = SearchEngine(
    llm="ollama/qwen2.5:14b",
    vision_llm="ollama/qwen2.5vl:7b",   # ~5 GB, enables image-grid solving
    captcha_min_confidence=0.7,
    captcha_max_attempts=2,
)
```

The `CaptchaSolver` chains them automatically: Tesseract first → vision LLM on low confidence → return best. `result.solver` tells you which one produced the answer.

Supported types: text OCR, reCAPTCHA v2 image grid, hCaptcha image grid (~50–80% success rate).
**Not supported:** reCAPTCHA v3 (invisible), Cloudflare Turnstile, Arkose 3D puzzles. These return `status="blocked"`.

```python
# When solver fails or type is unsupported:
result.status      # "blocked"
result.reason      # "captcha_unsupported"
result.suggestion  # "Use the official API: https://..."
```

### Change monitoring

Watch sites for changes, get notified.

```python
from vouch import Monitor

monitor = Monitor(engine)
monitor.watch(
    site="cvm.gov.br",
    query="resoluções recentes",
    interval="1h",
    notify_via="email",   # or "slack", "discord", "webhook"
)
monitor.start()
```

Uses 3-tier change detection: hash → diff → embedding similarity. **Avoids LLM calls when content is unchanged**, keeping monitoring cheap (~$1–3/month for 100 sites hourly with Gemini Flash-Lite).

### FastAPI dashboard

```bash
vouch serve --port 8080
# → web UI at http://localhost:8080
# → manage catalog, view cache, run searches, see costs
```

## Configuration reference

### `SearchEngine(...)`

```python
SearchEngine(
    # LLM
    llm: str | list[str] = "ollama/qwen2.5:14b",
    router_llm: str | None = None,        # defaults to llm
    vision_llm: str | None = None,        # disables CAPTCHA features if None
    api_keys: dict | None = None,
    
    # Routing
    router_strategy: str = "llm",         # "llm" | "embedding" | "all" | "tags"
    router_top_k: int = 3,
    router_explain: bool = False,
    
    # Search
    default_depth: int = 1,
    parallel_sites: int = 3,              # how many sites to search concurrently
    
    # Browser
    default_behavior: str = "natural",    # "natural" | "stealth" | "external"
    humanize: bool = True,
    typing_speed: str = "natural",
    headless: bool = True,
    
    # Caching
    cache_dir: str = "~/.vouch",
    cache_ttl_days: int = 30,
    
    # Politeness
    respect_robots_txt: bool = True,
    default_rate_limit: str = "2/min",
    user_agent: str | None = None,        # defaults to recent Chrome
    
    # Captcha (only if vision_llm is set)
    captcha_min_confidence: float = 0.7,
    captcha_max_attempts: int = 2,
    
    # Misc
    cache_dir: str = "~/.vouch",
    verbose: bool = False,
)
```

### `engine.search(...)`

```python
engine.search(
    query: str,
    depth: int = None,                # overrides default_depth
    sites: list[str] | None = None,   # restrict to specific sites
    only_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    max_results: int = 10,
    timeout: float = 60.0,
) -> SearchResult
```

### `SearchResult`

```python
SearchResult(
    query: str,
    chunks: list[Chunk],
    sites_searched: list[str],
    routing_decisions: list[RouteDecision],
    duration_ms: float,
    cost_estimate_usd: float,
    tokens_used: dict[str, int],   # {"input": ..., "output": ...}
    cache_stats: dict,             # {"hits": ..., "misses": ...}
)

Chunk(
    source_url: str,
    site: str,                     # "cvm.gov.br"
    site_category: str | None,
    title: str,
    snippet: str,                  # ~200 chars
    content: str | None,           # full markdown if depth >= 2
    relevance_score: float,        # 0–1
    extracted_at: datetime,
    metadata: dict,                # extra fields per adapter
)
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         SearchEngine                                 │
└──────────────────────────────────────────────────────────────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            │                                     │
            ▼                                     ▼
    ┌──────────────┐                     ┌──────────────┐
    │   Catalog    │                     │    Router    │
    │  (SQLite)    │ ─── metadata ────▶  │   (LLM/emb)  │
    └──────────────┘                     └──────────────┘
                                                  │
                                                  │ ranked sites
                                                  ▼
                                       ┌────────────────────┐
                                       │   parallel fetch   │
                                       └────────────────────┘
                                                  │
                  ┌───────────────────────────────┼───────────────────────────────┐
                  │                               │                               │
                  ▼                               ▼                               ▼
         ┌──────────────┐               ┌──────────────┐               ┌──────────────┐
         │ SiteAdapter  │               │ SiteAdapter  │               │ SiteAdapter  │
         │  cvm.gov.br  │               │  arxiv.org   │               │ news.yc.com  │
         │              │               │              │               │              │
         │ ┌──────────┐ │               │ ┌──────────┐ │               │ ┌──────────┐ │
         │ │ selector │ │               │ │ selector │ │               │ │ selector │ │
         │ │  cache   │ │               │ │  cache   │ │               │ │  cache   │ │
         │ └────┬─────┘ │               │ └────┬─────┘ │               │ └────┬─────┘ │
         │      │ MISS  │               │      │ HIT   │               │      │ HIT   │
         │      ▼       │               │      ▼       │               │      ▼       │
         │  discover    │               │   playwright │               │   playwright │
         │  via LLM     │               │   replay     │               │   replay     │
         └──────┬───────┘               └──────┬───────┘               └──────┬───────┘
                │                              │                              │
                └──────────────────────────────┴──────────────────────────────┘
                                               │
                                               ▼
                                    ┌────────────────────┐
                                    │  Aggregator/Rank   │
                                    └────────────────────┘
                                               │
                                               ▼
                                       SearchResult
```

### Module layout

```
vouch/
├── __init__.py            # public API: search, SearchEngine, Site
├── engine.py              # SearchEngine orchestrator
├── catalog.py             # Catalog (SQLite-backed Site registry)
├── models.py              # Site, Chunk, SearchResult, RouteDecision
├── config.py              # SearchEngine config dataclass
├── exceptions.py          # VouchError + back-compat CurioError alias
├── dns_resolver.py        # auto-fixes wrong-host catalog entries
├── plugins.py             # entry_points-based plugin discovery
├── cli.py                 # typer-based CLI (vouch ...)
├── server.py              # optional: FastAPI dashboard
├── _lang.py               # language detection helpers
├── _llm.py                # LiteLLM wrapper (sync + async)
├── router/
│   ├── base.py            # Router Protocol
│   ├── llm_router.py      # LLM-based routing (default)
│   ├── embedding_router.py# cosine-similarity routing
│   ├── tag_router.py      # tag-match routing
│   └── all_router.py      # "search every site" fallback
├── adapters/
│   ├── base.py            # SiteAdapter Protocol
│   ├── http.py            # depth=0, fast HTTP+Trafilatura
│   ├── browser.py         # depth=1+, Playwright
│   ├── browser_pool.py    # shared Chromium pool across searches
│   └── stealth.py         # patchright wrapper
├── discovery/
│   ├── search_bar.py      # LLM-powered selector discovery
│   ├── cache.py           # SQLite selector cache
│   ├── humanize.py        # lognormal pauses, typing, business hours
│   └── probe.py           # opt-in profile probe on add()
├── extraction/
│   ├── trafilatura.py     # HTML → markdown
│   ├── pdf.py             # PDF handling (pypdf)
│   ├── llm.py             # structured extraction via Pydantic
│   ├── llm_extract.py     # quality detector + LLM-driven extraction
│   └── css_selectors.py   # cached-selector replay (lxml.cssselect)
├── captcha/               # optional: Tesseract OCR + vision_llm CAPTCHA
│   ├── solver.py
│   └── tesseract.py
├── monitor/               # optional: change tracking + notifications
│   ├── watcher.py
│   └── notify.py
├── profiles/              # 24 curated site profiles + registry
│   ├── registry.py
│   ├── update.py
│   └── builtin.yaml
├── integrations/
│   ├── _common.py
│   ├── crewai.py          # VouchSearchTool (CrewAI)
│   ├── langchain.py       # VouchSearchTool (LangChain)
│   ├── pydantic_ai.py     # vouch_tool (PydanticAI)
│   └── mcp.py             # MCP server (Claude Desktop, Cursor)
```

### Key dependencies

- **playwright** — browser automation
- **litellm** — multi-LLM, BYOK, fallback chains
- **pydantic** v2 — models everywhere
- **sqlalchemy** + sqlite — catalog and cache
- **trafilatura** — fast HTML→markdown extraction
- **typer** — CLI
- **apscheduler** — optional, for monitor
- **fastapi** + **uvicorn** — optional, for dashboard
- **patchright** — optional, for stealth
- **sentence-transformers** — optional, for embedding router

No CrewAI/LangChain/etc as hard deps. They're integration extras only.

## Cost and performance

Typical numbers from internal runs. Depend heavily on LLM, network, site, and cache state — treat as rough order-of-magnitude, not a guarantee. Reproducible benchmark scripts under `examples/` if you want to validate on your stack.

### Per-search costs

Typical query, depth=1, 3 sites routed, all cache hits:

| LLM | Routing | Discovery | Extraction | **Total** |
|---|---|---|---|---|
| Ollama qwen2.5:14b | $0 | $0 (cached) | $0 | **$0** |
| Gemini Flash-Lite | $0.0001 | $0 (cached) | $0.001 | **~$0.001** |
| Claude Haiku 4.5 | $0.0005 | $0 (cached) | $0.005 | **~$0.005** |
| GPT-4.1-mini | $0.0003 | $0 (cached) | $0.003 | **~$0.003** |

First search on a new site adds ~$0.01–0.05 for discovery (one-time per site).

### Latency

- HTTP-only fetch (depth=0): ~1–3s/site
- Cached browser search (depth=1): ~2–5s/site
- First-time discovery (depth=1): ~8–15s/site
- Full content extraction (depth=2): ~15–40s/site

Searches across multiple sites run in parallel (controlled by `parallel_sites`).

### Hardware requirements

- **Pure HTTP mode**: any machine with Python
- **Browser mode**: 4GB RAM minimum, 8GB recommended
- **Local LLM mode**: depends on model. Qwen2.5:14b needs ~16GB RAM (CPU) or ~10GB VRAM
- **Vision mode**: Qwen2.5-VL 7B needs ~8GB VRAM

## Limits and what's out of scope

vouch is opinionated about what it tries to do and what it doesn't.

**What's in scope:**
- Public sites that respond well to standard web requests
- Sites where you want to discover search behavior dynamically
- Sites you've explicitly added to your catalog
- Polite, rate-limited, robots.txt-respecting access
- Educational, research, regulatory, professional use cases

**What's explicitly out of scope:**
- **Bypassing Cloudflare's modern bot protection** (Turnstile invisible, Bot Fight Mode aggressive). vouch includes humanize and stealth options that help with mild detection, but no open-source library reliably defeats current Cloudflare. For those cases, plug a commercial bypass service (Browserbase, Bright Data, ZenRows) via the `behavior="external"` site option.
- **Mass scraping** — vouch is built for "search across my list of trusted sources", not "scrape the entire web."
- **CAPTCHA solving as a sales pitch.** The optional vision-LLM CAPTCHA assist is best-effort and only works on simple visual challenges. It won't (and shouldn't) work on adversarial challenges.
- **Logged-in personal accounts (LinkedIn, Instagram, etc.)** — even when technically possible, this is usually a ToS violation. vouch supports authentication for sites where it's legitimate (gov portals, enterprise dashboards you own), not for this.

This isn't a limitation we apologize for — it's the position. A library that promises to bypass everything breaks every week and isn't sustainable as open-source.

## Roadmap

**v0.1 (initial release):**
- Levels 1–3 API
- HTTP + browser adapters
- LLM router (single strategy)
- Selector cache
- Ollama + major API providers via LiteLLM
- CrewAI + LangChain integrations
- CLI

**v0.2:**
- Embedding router
- Vision-LLM CAPTCHA assist
- MCP server
- PydanticAI integration

**v0.3:**
- Change monitoring
- FastAPI dashboard
- Stealth mode (patchright)
- Auth flow helpers

**v0.4+:**
- Distributed search workers
- Built-in vector DB for content reuse
- Better PDF extraction (Docling)
- Workflow chains (search → reason → search)

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Quick start for dev:

```bash
git clone https://github.com/YOURUSER/vouch
cd vouch
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,all]"
playwright install chromium
pytest
```

Issues, PRs, ideas welcome. Especially:
- New `SiteAdapter` implementations (specific site optimizations)
- New `Router` strategies
- Integrations with other agent frameworks
- Translations of docs

## References and prior art

vouch stands on the shoulders of these projects. Read their docs — most of them solve adjacent problems brilliantly.

### Direct inspiration

- **[Tavily](https://tavily.com)** & **[Exa](https://exa.ai)** — defined the "search API for agents" category. vouch is "Tavily, but for your own sources."
- **[Kagi Lenses](https://help.kagi.com/kagi/features/lenses.html)** & **[Brave Goggles](https://search.brave.com/help/goggles)** — proved curated-source search is a real product. vouch brings it to OSS.
- **[Skyvern](https://github.com/Skyvern-AI/skyvern)** — pioneered "discover-then-cache" for browser automation. vouch applies the same pattern to search specifically.
- **[Stagehand](https://github.com/browserbase/stagehand)** — `act()` / `observe()` API inspired the discovery layer.

### Building blocks used

- **[Playwright](https://playwright.dev)** — browser automation
- **[browser-use](https://github.com/browser-use/browser-use)** — DOM-to-LLM serialization patterns
- **[Crawl4AI](https://github.com/unclecode/crawl4ai)** — extraction strategies, JsonCssExtractionStrategy
- **[LiteLLM](https://github.com/BerriAI/litellm)** — multi-provider LLM client
- **[Trafilatura](https://github.com/adbar/trafilatura)** — HTML to clean text
- **[Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)** — stealth Playwright
- **[Camoufox](https://github.com/daijro/camoufox)** — for serious anti-fingerprinting
- **[semantic-router](https://github.com/aurelio-labs/semantic-router)** — embedding-based routing patterns
- **[APScheduler](https://github.com/agronholm/apscheduler)** — for the optional monitor module
- **[Apprise](https://github.com/caronc/apprise)** — 100+ notification channels for monitor

### Adjacent projects worth knowing

- **[Perplexica](https://github.com/ItzCrazyKns/Perplexica)** — open-source Perplexity clone (open-web)
- **[gpt-researcher](https://github.com/assafelovic/gpt-researcher)** — research agent (open-web)
- **[local-deep-research](https://github.com/LearningCircuit/local-deep-research)** — local research bot (engine-based, not site-based)
- **[changedetection.io](https://github.com/dgtlmoon/changedetection.io)** — site change tracking (no LLM extraction)
- **[bdambrosio/llmsearch](https://github.com/bdambrosio/llmsearch)** — small precedent for source-curated LLM search
- **[Firecrawl](https://github.com/firecrawl/firecrawl)** — `/search` endpoint backed by Google/Bing
- **[ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai)** — LLM-driven scraping
- **[SearXNG](https://github.com/searxng/searxng)** — federated meta-search engine

### Reading

- *Stagehand caching internals*: https://www.browserbase.com/blog/stagehand-caching
- *Skyvern adaptive caching*: https://github.com/Skyvern-AI/skyvern (recent PRs)
- *Anti-detection landscape 2026*: https://github.com/pim97/anti-detect-browser-tools-tech-comparison
- *LLM Gateway comparison*: https://github.com/BerriAI/litellm

## License

MIT — see [`LICENSE`](LICENSE).

## Acknowledgments

Built by [@evertonsjjj](https://github.com/evertonsjjj). Early-stage open source — looking for real-world feedback, contributors, and battle-tested use cases. The gap this fills (curated-source search for agents) is one I needed myself, but I'd rather hear what's wrong with it from people using it than guess in isolation.

If vouch helps you, a ⭐ on GitHub goes a long way.
