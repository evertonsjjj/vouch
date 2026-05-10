# Contributing to farol

Thanks for considering a contribution. farol is an early-stage project — issues, PRs, and ideas are all welcome.

## Development setup

```bash
git clone https://github.com/yourhandle/farol
cd farol
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev,all]"
playwright install chromium
pytest
```

## Project layout

See the [Architecture](README.md#architecture) section of the README. Each major component is a `Protocol` you can replace — keep that contract in mind when adding features.

## Style

- `ruff` for linting and formatting (`ruff check . && ruff format .`).
- `mypy` for type-checking the core modules.
- Docstrings on public API. No comment spam internally.
- Tests for every new public function or protocol implementation.

## Commit / PR conventions

- One logical change per PR.
- Reference an issue when one exists.
- Run `pytest` and `ruff check .` before pushing.
- Keep `README.md` in sync when public API changes.

## Areas we want help with

- New `SiteAdapter` implementations (per-site optimizations).
- New `Router` strategies.
- Integrations with other agent frameworks.
- Translations (English / Português / Español).
- Real-world catalogs as YAML examples (regulatory, academic, news).

## Code of conduct

Be kind. Be specific. Assume good faith. Reviewers and contributors give their time freely — make their job easier with clear context.
