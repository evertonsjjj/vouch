"""Site model and SQLite-backed catalog."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import tldextract
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Engine,
    String,
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .config import Behavior
from .exceptions import CatalogError


def _normalize_domain(url: str) -> str:
    """Strip scheme/path; keep registered domain. ``cvm.gov.br`` stays as-is."""
    if not url:
        raise CatalogError("Site url is required")
    raw = url.strip()
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = parsed.netloc or parsed.path
    host = host.split("/")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host


class Site(BaseModel):
    """Declarative source descriptor.

    All metadata fields are optional. Provide what helps the router and the
    operator; leave the rest blank.
    """

    url: str
    category: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)

    behavior: Behavior = "natural"
    rate_limit: str | None = None
    requires_login: bool = False
    search_url_template: str | None = None

    pre_search: Callable[..., Any] | None = None
    post_extract: Callable[..., Any] | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, url: str | None = None, /, **data: Any) -> None:
        # Accept ``Site("cvm.gov.br")`` per README, in addition to ``Site(url=...)``.
        if url is not None:
            data.setdefault("url", url)
        super().__init__(**data)

    @field_validator("url", mode="after")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return _normalize_domain(v)

    @field_validator("tags", mode="before")
    @classmethod
    def _ensure_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return list(v)

    @property
    def domain(self) -> str:
        return self.url

    @property
    def registered_domain(self) -> str:
        ext = tldextract.extract(self.url)
        return ext.registered_domain or self.url

    @property
    def homepage(self) -> str:
        return f"https://{self.url}"

    def routing_blob(self) -> str:
        parts = [self.url]
        if self.category:
            parts.append(f"category: {self.category}")
        if self.description:
            parts.append(self.description)
        if self.tags:
            parts.append("tags: " + ", ".join(self.tags))
        return " | ".join(parts)


# --- SQLAlchemy persistence -------------------------------------------------


class _Base(DeclarativeBase):
    pass


class _SiteRow(_Base):
    __tablename__ = "sites"

    url: Mapped[str] = mapped_column(String(255), primary_key=True)
    category: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    behavior: Mapped[str] = mapped_column(String(32), default="natural")
    rate_limit: Mapped[str | None] = mapped_column(String(64))
    requires_login: Mapped[bool] = mapped_column(Boolean, default=False)
    search_url_template: Mapped[str | None] = mapped_column(String(512))
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @classmethod
    def from_site(cls, site: Site) -> _SiteRow:
        return cls(
            url=site.url,
            category=site.category,
            description=site.description,
            tags=list(site.tags),
            behavior=site.behavior,
            rate_limit=site.rate_limit,
            requires_login=site.requires_login,
            search_url_template=site.search_url_template,
            extra={},
        )

    def to_site(self) -> Site:
        return Site(
            url=self.url,
            category=self.category,
            description=self.description,
            tags=list(self.tags or []),
            behavior=self.behavior or "natural",
            rate_limit=self.rate_limit,
            requires_login=bool(self.requires_login),
            search_url_template=self.search_url_template,
        )


class Catalog:
    """SQLite-backed collection of Sites. Thread-safe for read-heavy use."""

    def __init__(self, path: str | Path | None = None, *, engine: Engine | None = None):
        if engine is None:
            if path is None:
                self._engine = create_engine("sqlite:///:memory:", future=True)
            else:
                p = Path(path)
                p.parent.mkdir(parents=True, exist_ok=True)
                self._engine = create_engine(f"sqlite:///{p}", future=True)
        else:
            self._engine = engine
        _Base.metadata.create_all(self._engine)
        # Live callable hooks aren't persisted — store them in-memory.
        self._hooks: dict[str, dict[str, Callable]] = {}

    # CRUD -----------------------------------------------------------------

    def add(self, site: Site, *, replace: bool = False, resolve_dns: bool = False) -> Site:
        """Persist a Site. Pass ``resolve_dns=True`` to probe canonical hostname."""
        if resolve_dns:
            try:
                from .dns_resolver import resolve_canonical_host

                canonical = resolve_canonical_host(site.url)
                if canonical and canonical != site.url:
                    site = site.model_copy(update={"url": canonical})
            except Exception:
                # never block add() on a DNS probe failure
                pass
        with Session(self._engine) as s:
            existing = s.get(_SiteRow, site.url)
            if existing and not replace:
                raise CatalogError(
                    f"Site {site.url!r} already exists; pass replace=True to overwrite."
                )
            row = _SiteRow.from_site(site)
            s.merge(row)
            s.commit()
        if site.pre_search or site.post_extract:
            self._hooks[site.url] = {
                "pre_search": site.pre_search,
                "post_extract": site.post_extract,
            }
        return site

    def get(self, url: str) -> Site | None:
        url = _normalize_domain(url)
        with Session(self._engine) as s:
            row = s.get(_SiteRow, url)
            if not row:
                return None
            site = row.to_site()
        hooks = self._hooks.get(url, {})
        if hooks:
            site = site.model_copy(update=hooks)
        return site

    def remove(self, url: str) -> bool:
        url = _normalize_domain(url)
        with Session(self._engine) as s:
            row = s.get(_SiteRow, url)
            if not row:
                return False
            s.delete(row)
            s.commit()
        self._hooks.pop(url, None)
        return True

    def update(self, url: str, **fields) -> Site:
        url = _normalize_domain(url)
        with Session(self._engine) as s:
            row = s.get(_SiteRow, url)
            if not row:
                raise CatalogError(f"Unknown site {url!r}")
            for k, v in fields.items():
                if k == "tags":
                    row.tags = list(v or [])
                elif hasattr(row, k):
                    setattr(row, k, v)
            s.commit()
            s.refresh(row)
            return row.to_site()

    def list(self, *, only_tags: Iterable[str] | None = None) -> list[Site]:
        with Session(self._engine) as s:
            rows = list(s.scalars(select(_SiteRow)).all())
        sites = [r.to_site() for r in rows]
        if only_tags:
            wanted = set(only_tags)
            sites = [si for si in sites if wanted & set(si.tags)]
        return sites

    def __len__(self) -> int:
        with Session(self._engine) as s:
            return len(list(s.scalars(select(_SiteRow.url)).all()))

    def __contains__(self, url: str) -> bool:
        return self.get(url) is not None

    # Bulk ops -------------------------------------------------------------

    def add_many(self, sites: Iterable[Site], *, replace: bool = True) -> list[Site]:
        added = []
        for s in sites:
            try:
                added.append(self.add(s, replace=replace))
            except CatalogError:
                if not replace:
                    raise
        return added

    def export_yaml(self) -> str:
        import yaml

        rows = [
            {
                "url": s.url,
                **({"category": s.category} if s.category else {}),
                **({"description": s.description} if s.description else {}),
                **({"tags": s.tags} if s.tags else {}),
                **({"behavior": s.behavior} if s.behavior != "natural" else {}),
                **({"rate_limit": s.rate_limit} if s.rate_limit else {}),
                **({"requires_login": True} if s.requires_login else {}),
                **({"search_url_template": s.search_url_template} if s.search_url_template else {}),
            }
            for s in self.list()
        ]
        return yaml.safe_dump({"sites": rows}, sort_keys=False, allow_unicode=True)

    @classmethod
    def from_yaml(cls, path: str | Path, *, db_path: str | Path | None = None) -> Catalog:
        cat = cls(db_path)
        cat.load_yaml(path, replace=True)
        return cat

    def load_yaml(self, path: str | Path, *, replace: bool = True) -> list[Site]:
        import yaml

        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        raw_sites = data.get("sites") or []
        sites = [Site(**row) for row in raw_sites]
        return self.add_many(sites, replace=replace)

    def to_dicts(self) -> list[dict]:
        return [json.loads(s.model_dump_json()) for s in self.list()]
