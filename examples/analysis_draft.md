# 90-query benchmark — analysis (working draft)

This draft is filled in as the benchmark runs and gets finalized in chat.

## Failure modes observed in the wild

| Symptom | Sites affected | Root cause | Fix tier |
|---|---|---|---|
| `403 Forbidden` on first request | jusbrasil, elpais, en/pt-wikipedia, stackoverflow | UA-based bot detection | UA rotation + stealth + browser |
| Intermittent `502 Bad Gateway` | folha.uol.com.br | Server overload or rate-limit | retry-after + backoff |
| `getaddrinfo failed` (DNS) | agenciatributaria.es | Wrong hostname (real one is `sede.agenciatributaria.gob.es`) | catalog lint + auto-resolve on add |
| First chunk = category nav ("Benefits", "History & Society") | britannica, gov.uk | Static HTML returned + heuristic + LLM both pick first salient anchor | Smarter quality check; CSS-selector pinning |
| First chunk = recursive search URL | pypi (own) | Search page links back to itself | filter out same-as-page-url |
| Empty results, no errors | MDN, pypi (results page) | JS-rendered SPA — server returns shell | Auto-escalate to BrowserAdapter |

## What worked

- Router LLM picked the right site for the query in **every observed case** (PT-tax → jusbrasil, EN-tax → gov.uk, ES-tax → agenciatributaria, ES-gen → elpais, etc.). Routing is the easy part.
- Templated HTTP search executes in 4-7s.
- LLM extraction fallback recovered HuggingFace and GitHub from total nav-junk to real model/repo names.
- Cost: $0 with Ollama qwen2.5:7b across all 90 queries.
- Selector cache persists between calls.

## What didn't work

- Heuristic + LLM extraction both fooled when the entire results page is dominated by site-section nav (gov.uk, britannica). The LLM picks "Benefits" because it doesn't have access to enough DOM context to know it's a megamenu link, not a result.
- 403 sites can't be saved by any extraction logic — request never returns useful HTML.
- Spanish-tax queries: 100% failure because both candidate sites (jusbrasil, agenciatributaria) failed for different reasons (403 / DNS).
