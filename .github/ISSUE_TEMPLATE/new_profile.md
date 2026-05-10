---
name: New site profile
about: Submit a curated profile for a popular site
title: "[profile] add <domain>"
labels: profile
---

**Domain**
e.g. `example.com`

**Why curate this site?**
What category, language, audience? Why should curio's users know about it?

**Suggested profile YAML**

```yaml
- url: example.com
  category: ...
  description: >
    ...
  tags: [..., ...]
  search_url_template: "/search?q={query}"
```

**Notes on extraction**

- Does it block default UA? (yes/no)
- Server-rendered or JS-only?
- Any anti-bot WAF (Cloudflare, DataDome, …)?

**Sample search you tested**

`<query that works>` →  expect to find  `<sample result title>`
