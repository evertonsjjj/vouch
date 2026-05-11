# Writing a vouch plugin

vouch discovers plugins via Python's standard `entry_points` mechanism — the
same one [pytest](https://docs.pytest.org/en/stable/how-to/writing_plugins.html)
and [click](https://click.palletsprojects.com/en/stable/setuptools/) use.
A plugin is just a regular Python package published to PyPI; once a user
does `pip install vouch-adapter-arxiv` (or whatever you name it), the next
`SearchEngine()` in their project picks it up automatically.

Three plugin groups are supported:

| Group               | What it provides                                      |
|---------------------|-------------------------------------------------------|
| `vouch.adapters`    | per-host search executors with hand-tuned extraction  |
| `vouch.routers`     | alternative router strategies (e.g. RAG, vector DB)   |
| `vouch.profiles`    | curated `ProfileRegistry` for a set of sites          |

## Example: adapter plugin

Suppose arxiv's heuristic extraction is good enough but you want to
hard-code selectors so first-time use is instant.

```python
# my_arxiv_plugin/__init__.py
from vouch.adapters.base import AdapterContext, SiteAdapter
from vouch.models import Chunk


class ArxivAdapter(SiteAdapter):
    def __init__(self, *, config, llm=None, selector_cache=None, **kwargs):
        self.config = config

    def search(self, ctx: AdapterContext) -> list[Chunk]:
        # ... your hand-tuned arxiv extraction here ...
        return [...]

    def close(self) -> None:
        pass


def make(*, site, config, llm=None, selector_cache=None, pool=None, **kwargs):
    """Factory called by vouch's build_adapter when site.url matches."""
    return ArxivAdapter(config=config, llm=llm, selector_cache=selector_cache)
```

Declare it in your `pyproject.toml`:

```toml
[project]
name = "vouch-adapter-arxiv"
version = "0.1.0"
dependencies = ["vouch>=0.2"]

[project.entry-points."vouch.adapters"]
"arxiv.org" = "my_arxiv_plugin:make"
```

Now `pip install vouch-adapter-arxiv` is enough — `build_adapter(site)`
will call your factory whenever `site.url == "arxiv.org"`.

### Host patterns

The entry point **name** can be:

- An exact host: `"arxiv.org"`
- A suffix wildcard: `"*.gov.br"` (matches `cvm.gov.br`, `receita.gov.br`, ...)
- The catch-all `"*"` — for fallback adapters that want a shot at every site

When multiple plugins claim the same host, **exact matches win, then the
longest suffix, then the catch-all**.

## Example: profile registry plugin

If you maintain a curated bundle of `Site` profiles for a domain
(BR tax law, EU regulators, ML community blogs, …), publish them as a
profile-registry plugin:

```python
# vouch_profiles_br_tax/__init__.py
from vouch.profiles import ProfileRegistry


def registry() -> ProfileRegistry:
    return ProfileRegistry.from_yaml("path/to/br_tax_profiles.yaml")
```

```toml
[project.entry-points."vouch.profiles"]
"br-tax" = "vouch_profiles_br_tax:registry"
```

After install, `vouch.get_profile("cvm.gov.br")` returns your curated entry
even though it's not in vouch's `builtin.yaml`.

## Example: router plugin

If you want a router that asks a vector DB instead of the LLM:

```python
# vouch_router_pinecone/__init__.py
from vouch.router.base import Router, RoutingContext
from vouch.models import RouteDecision


class PineconeRouter(Router):
    def __init__(self, **kwargs):
        ...

    def route(self, ctx: RoutingContext) -> list[RouteDecision]:
        ...
```

```toml
[project.entry-points."vouch.routers"]
"pinecone" = "vouch_router_pinecone:PineconeRouter"
```

End users then opt in via:

```python
from vouch import SearchEngine
from vouch.plugins import find_router_factory

router_cls = find_router_factory("pinecone")
engine = SearchEngine(router=router_cls(index_name="..."))
```

## Listing what's installed

```bash
vouch plugins list
```

prints the names of all installed adapter / router / profile plugins.
