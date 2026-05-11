---
name: Bug report
about: Something isn't working as expected
title: "[bug] "
labels: bug
---

**What happened?**
A clear and concise description.

**Reproducer**

```python
from vouch import SearchEngine, Site
engine = SearchEngine(llm="ollama/qwen2.5:7b")
engine.add(Site("..."))
result = engine.search("...")
```

**Expected vs actual**

- Expected: ...
- Actual: ...

**Environment**

- OS: <Windows / macOS / Linux>
- Python: <output of `python --version`>
- vouch: <output of `vouch --version`>
- Extras installed: <`browser`, `stealth`, `monitor`, etc.>

**Logs / traceback**

```
<paste here>
```
