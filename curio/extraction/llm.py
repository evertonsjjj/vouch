"""Structured extraction via Pydantic schemas."""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from .._llm import LLMClient

T = TypeVar("T", bound=BaseModel)

_SYS = (
    "You extract structured data from web content. Return strict JSON that matches the "
    "provided schema exactly. If a field is unknown, use null. No prose."
)


def extract_structured(
    text: str,
    schema: type[T],
    *,
    llm: LLMClient,
    instructions: str = "Extract the relevant fields.",
) -> T:
    """Run a structured extraction over *text* using *schema*.

    Returns a populated instance of the Pydantic model, or raises ValidationError.
    """
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    prompt = f"{instructions}\n\nJSON schema:\n{schema_json}\n\nSource content:\n{text[:8000]}"
    data = llm.chat_json(
        [{"role": "system", "content": _SYS}, {"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=2000,
    )
    return schema.model_validate(data)


__all__ = ["extract_structured"]
