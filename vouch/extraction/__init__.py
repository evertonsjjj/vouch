"""Content extraction — HTML, PDF, and structured (LLM-based)."""

from __future__ import annotations

from .trafilatura import extract_main_text, to_chunks

__all__ = ["extract_main_text", "to_chunks"]
