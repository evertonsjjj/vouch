"""LLM-powered discovery of a site's search interface.

We do NOT pass full HTML to the LLM. Instead, we pass a compact representation
of candidate inputs/buttons (selector + label/placeholder/role) extracted by
JavaScript in the page. The LLM picks the best pair.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .._llm import LLMClient

log = logging.getLogger("curio.discovery")

_SCAN_JS = r"""
() => {
  const css = (el) => {
    if (!el) return null;
    if (el.id) return '#' + CSS.escape(el.id);
    let parts = [];
    let n = el;
    while (n && n.nodeType === 1 && parts.length < 6) {
      let p = n.tagName.toLowerCase();
      if (n.classList && n.classList.length) {
        const c = Array.from(n.classList).slice(0, 2).map(x => '.' + CSS.escape(x)).join('');
        p += c;
      }
      const sib = n.parentNode ? Array.from(n.parentNode.children).filter(s => s.tagName === n.tagName) : [];
      if (sib.length > 1) p += `:nth-of-type(${sib.indexOf(n) + 1})`;
      parts.unshift(p);
      n = n.parentNode;
    }
    return parts.join(' > ');
  };
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = window.getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
  };
  const inputs = [];
  document.querySelectorAll('input,textarea,[role="searchbox"],[contenteditable="true"]').forEach(el => {
    if (!visible(el)) return;
    const t = (el.getAttribute('type') || '').toLowerCase();
    if (t && !['text','search','email','url',''].includes(t)) return;
    inputs.push({
      sel: css(el),
      type: t,
      name: el.getAttribute('name') || '',
      placeholder: el.getAttribute('placeholder') || '',
      aria: el.getAttribute('aria-label') || '',
      role: el.getAttribute('role') || el.tagName.toLowerCase(),
    });
  });
  const buttons = [];
  document.querySelectorAll('button,input[type="submit"],[role="button"],a').forEach(el => {
    if (!visible(el)) return;
    const txt = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
    if (!txt && !(el.querySelector && el.querySelector('svg'))) return;
    buttons.push({
      sel: css(el),
      text: txt.slice(0, 80),
      aria: el.getAttribute('aria-label') || '',
    });
  });
  return { inputs: inputs.slice(0, 30), buttons: buttons.slice(0, 40) };
}
"""

_SYS = (
    "You inspect a candidate list of inputs and buttons from a website's homepage and "
    "identify which combination acts as the site's search bar. Output strict JSON only."
)

_USER = """Site: {site}
User wants to search for: {query}

Candidate inputs:
{inputs}

Candidate buttons:
{buttons}

Pick the best search input and (optionally) the submit button.
Return JSON:
{{
  "input": "<css-selector for the input>",
  "submit": "<css-selector for submit, or null if pressing Enter is enough>",
  "confidence": 0.0-1.0,
  "rationale": "<one-sentence reason>"
}}

If no input on this page acts as a search bar, return {{"input": null}}."""


async def discover_selectors(page: Any, query: str, *, llm: LLMClient, site=None) -> dict | None:
    """Inspect *page* and return ``{"input": <sel>, "submit": <sel|None>, ...}``."""
    try:
        candidates = await page.evaluate(_SCAN_JS)
    except Exception as e:  # noqa: BLE001
        log.warning("DOM scan failed: %s", e)
        return None

    inputs = candidates.get("inputs", [])
    buttons = candidates.get("buttons", [])
    if not inputs:
        return None

    prompt = _USER.format(
        site=getattr(site, "url", page.url),
        query=query,
        inputs=json.dumps(inputs, ensure_ascii=False, indent=1),
        buttons=json.dumps(buttons, ensure_ascii=False, indent=1),
    )
    data = llm.chat_json(
        [{"role": "system", "content": _SYS}, {"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=400,
    )
    if not isinstance(data, dict):
        return None
    if not data.get("input"):
        return None
    out = {
        "input": data.get("input"),
        "submit": data.get("submit"),
        "confidence": float(data.get("confidence", 0.7)),
        "rationale": data.get("rationale", ""),
    }
    log.info("Discovered selectors for %s: %s", getattr(site, "url", page.url), out)
    return out


__all__ = ["discover_selectors"]
