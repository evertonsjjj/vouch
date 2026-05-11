"""PDF text extraction. Lazy-loads pypdf so the base install stays slim."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from ..exceptions import ExtractionError


def extract_pdf_text(data: bytes | str | Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as e:
        raise ExtractionError(
            "PDF extraction requires pypdf. Install with: pip install 'vouch[pdf]'"
        ) from e

    if isinstance(data, (str, Path)):
        reader = PdfReader(str(data))
    else:
        reader = PdfReader(BytesIO(data))
    chunks = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n\n".join(c for c in chunks if c).strip()


__all__ = ["extract_pdf_text"]
