"""SQLite-backed selector cache.

Keyed by (domain, dom_fingerprint). When the cache fails on replay (target
no longer matches), callers should invalidate the entry and re-discover.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Engine,
    Integer,
    String,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class _Base(DeclarativeBase):
    pass


class _SelectorRow(_Base):
    __tablename__ = "selectors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    selectors: Mapped[dict] = mapped_column(JSON)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    fails: Mapped[int] = mapped_column(Integer, default=0)
    discovered_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used = Column(DateTime(timezone=True), server_default=func.now())


def fingerprint_html(html: str | None) -> str:
    """Stable-ish hash of structural HTML — used as a cache version key."""
    if not html:
        return "empty"
    h = hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return h


class SelectorCache:
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

    # ---- read --------------------------------------------------------

    def get(self, domain: str, fingerprint: str | None = None) -> dict | None:
        with Session(self._engine) as s:
            from sqlalchemy import select

            stmt = select(_SelectorRow).where(_SelectorRow.domain == domain)
            if fingerprint:
                stmt = stmt.where(_SelectorRow.fingerprint == fingerprint)
            row = s.scalars(stmt.order_by(_SelectorRow.last_used.desc())).first()
            if not row:
                return None
            row.hits += 1
            row.last_used = datetime.now(timezone.utc)
            s.commit()
            return dict(row.selectors)

    # ---- write -------------------------------------------------------

    def set(self, domain: str, selectors: dict[str, Any], *, fingerprint: str | None = None) -> None:
        fp = fingerprint or "v1"
        with Session(self._engine) as s:
            from sqlalchemy import select

            existing = s.scalars(
                select(_SelectorRow)
                .where(_SelectorRow.domain == domain)
                .where(_SelectorRow.fingerprint == fp)
            ).first()
            if existing:
                existing.selectors = selectors
                existing.last_used = datetime.now(timezone.utc)
            else:
                s.add(_SelectorRow(domain=domain, fingerprint=fp, selectors=selectors))
            s.commit()

    def record_failure(self, domain: str, fingerprint: str | None = None) -> None:
        with Session(self._engine) as s:
            from sqlalchemy import select

            stmt = select(_SelectorRow).where(_SelectorRow.domain == domain)
            if fingerprint:
                stmt = stmt.where(_SelectorRow.fingerprint == fingerprint)
            row = s.scalars(stmt).first()
            if row:
                row.fails += 1
                s.commit()

    def invalidate(self, domain: str) -> int:
        with Session(self._engine) as s:
            from sqlalchemy import delete

            res = s.execute(delete(_SelectorRow).where(_SelectorRow.domain == domain))
            s.commit()
            return int(res.rowcount or 0)

    # ---- stats -------------------------------------------------------

    def stats(self) -> dict[str, dict]:
        from sqlalchemy import select

        with Session(self._engine) as s:
            rows = list(s.scalars(select(_SelectorRow)).all())
        return {
            r.domain: {
                "discovered": r.discovered_at.isoformat() if r.discovered_at else None,
                "hits": r.hits,
                "fails": r.fails,
                "fingerprint": r.fingerprint,
            }
            for r in rows
        }

    def export_json(self) -> str:
        return json.dumps(self.stats(), default=str, indent=2)

    def __len__(self) -> int:
        from sqlalchemy import select

        with Session(self._engine) as s:
            return len(list(s.scalars(select(_SelectorRow.id)).all()))

    def __bool__(self) -> bool:
        # Always truthy: callers want "do I have a cache instance" not "is it empty".
        return True

    def touch(self) -> None:
        # Used as a no-op write to ensure the SQLite file exists.
        with Session(self._engine) as s:
            s.execute(_SelectorRow.__table__.select())
            s.commit()


__all__ = ["SelectorCache", "fingerprint_html"]

_TS = time.time
