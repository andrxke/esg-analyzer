"""The one place a real LLM provider and API key are wired.

OpenRouter is OpenAI-compatible, so this is a thin `LLMClient` over its Chat
Completions API. The core pipeline never imports this — it depends only on the
`LLMClient` Protocol in adapters.py. Only the edges (the golden-set eval and the
build-time batch) construct a real client here.

Design points held from the adapters seam:
- The SDK is lazy-imported, so importing this module never requires `openai`.
- The key is read from OPENROUTER_API_KEY — never hardcoded, never committed.
- Swap this class if you pick a different provider; callers only need .complete().

    pip install openai
    export OPENROUTER_API_KEY=sk-or-...
    export ESG_EVAL_MODEL=anthropic/claude-3.5-sonnet   # optional; pins a model
"""

from __future__ import annotations

import os

DEFAULT_MODEL = os.environ.get("ESG_EVAL_MODEL", "openrouter/auto")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Tier-2 replies are small structured JSON; keep the cap tight to bound cost.
MAX_TOKENS = 2000


class OpenRouterClient:
    """Thin LLMClient over OpenRouter's OpenAI-compatible Chat Completions API."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self._client = None

    def _ensure(self):
        if self._client is not None:
            return
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise SystemExit(
                "The LLM pass needs the 'openai' package (OpenRouter is "
                "OpenAI-compatible): pip install openai"
            ) from exc
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise SystemExit(
                "Set OPENROUTER_API_KEY to run against a live model.\n"
                "Get a key at https://openrouter.ai/keys"
            )
        self._client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=key)

    def complete(self, prompt: str, report_text: str) -> str:  # pragma: no cover - network
        self._ensure()
        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""
