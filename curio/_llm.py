"""Thin wrapper over LiteLLM with retries, fallback chains, and cost tracking."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .exceptions import LLMError
from .models import TokenUsage

log = logging.getLogger("curio.llm")


def _apply_keys(api_keys: dict[str, str] | None) -> None:
    if not api_keys:
        return
    mapping = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "google": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "cohere": "COHERE_API_KEY",
        "azure": "AZURE_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }
    for provider, key in api_keys.items():
        env = mapping.get(provider.lower(), provider.upper() + "_API_KEY")
        os.environ.setdefault(env, key)


# Approximate per-million-token pricing — used only for estimates, not billing.
_PRICE = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-7": (15.0, 75.0),
    "gpt-4.1-mini": (0.15, 0.6),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4.1": (5.0, 15.0),
    "gemini-2.5-flash": (0.075, 0.3),
    "gemini-2.5-flash-lite": (0.04, 0.15),
    "gemini-2.5-pro": (1.25, 5.0),
    "qwen2.5": (0.0, 0.0),
    "llama3": (0.0, 0.0),
    "ollama": (0.0, 0.0),
}


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    key = next((k for k in _PRICE if k in model), "ollama")
    pin, pout = _PRICE[key]
    return (tokens_in * pin + tokens_out * pout) / 1_000_000


class LLMClient:
    """Wraps litellm.completion with fallback chain + token accounting."""

    def __init__(self, model: str | list[str], api_keys: dict[str, str] | None = None):
        self.models = [model] if isinstance(model, str) else list(model)
        if not self.models:
            raise ValueError("LLMClient requires at least one model")
        _apply_keys(api_keys)
        self.tokens = TokenUsage()
        self.cost_usd = 0.0

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _call_one(self, model: str, messages: list[dict], **kwargs) -> dict:
        import litellm

        # Avoid noisy "Provider List" logs.
        litellm.suppress_debug_info = True
        return litellm.completion(model=model, messages=messages, **kwargs)

    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict | None = None,
        timeout: float | None = 60,
        **kwargs,
    ) -> str:
        last_err: Exception | None = None
        for model in self.models:
            try:
                resp = self._call_one(
                    model,
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    timeout=timeout,
                    **kwargs,
                )
                txt, usage = _extract(resp)
                self.tokens = self.tokens.add(usage)
                self.cost_usd += estimate_cost(model, usage.input, usage.output)
                return txt
            except Exception as e:
                log.warning("LLM call to %s failed: %s", model, e)
                last_err = e
        raise LLMError(f"All LLM models failed. Last error: {last_err}")

    def chat_json(self, messages: list[dict], **kwargs) -> Any:
        """Force JSON output and parse. Falls back to first JSON-looking block."""
        kwargs.setdefault("response_format", {"type": "json_object"})
        kwargs.setdefault("temperature", 0.0)
        try:
            txt = self.chat(messages, **kwargs)
        except LLMError:
            kwargs.pop("response_format", None)
            txt = self.chat(messages, **kwargs)
        return _parse_json_loose(txt)

    def vision(
        self,
        prompt: str,
        image_b64: str,
        *,
        mime: str = "image/png",
        **kwargs,
    ) -> str:
        msg = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                    },
                ],
            }
        ]
        return self.chat(msg, **kwargs)


def _extract(resp) -> tuple[str, TokenUsage]:
    try:
        msg = resp.choices[0].message
        text = msg.content or ""
    except Exception as e:
        raise LLMError(f"Could not extract message from LLM response: {e}") from e
    usage = getattr(resp, "usage", None) or {}
    pin = getattr(usage, "prompt_tokens", None) or usage.get("prompt_tokens", 0) if usage else 0
    pout = (
        getattr(usage, "completion_tokens", None) or usage.get("completion_tokens", 0)
        if usage
        else 0
    )
    return text, TokenUsage(input=int(pin or 0), output=int(pout or 0))


_JSON_BLOCK = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)


def _parse_json_loose(text: str) -> Any:
    text = text.strip()
    # Strip markdown fences.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        m = _JSON_BLOCK.search(text)
        if not m:
            raise LLMError(f"Could not parse JSON from LLM output: {text[:200]!r}") from None
        return json.loads(m.group(0))
