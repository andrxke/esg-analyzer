#!/usr/bin/env python3
"""CLI runner for the golden-set eval.

    python3 eval/run_eval.py                 # uses eval/golden.json
    python3 eval/run_eval.py path/to/manifest.json

This is the ONE place that wires a real LLM provider and a real API key. The
harness (esg_analyzer/eval_harness.py) stays provider-agnostic and testable with
fakes; only this runner touches the network.

Provider wiring is deliberately behind a lazy import + explicit env checks so the
repo runs (and the test suite passes) with zero installs and no key. To actually
score real reports:

    pip install anthropic
    export ANTHROPIC_API_KEY=sk-...
    python3 eval/run_eval.py

Provider is OpenRouter (OpenAI-compatible API). Set your key in the environment
— NEVER in code or committed files:

    pip install openai
    export OPENROUTER_API_KEY=sk-or-...
    python3 eval/run_eval.py

Model defaults to a current Claude generation via OpenRouter; override with
    export ESG_EVAL_MODEL=anthropic/claude-3.5-sonnet
Swap OpenRouterClient if you later pick a different provider — the harness only
needs .complete().
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running as `python3 eval/run_eval.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from esg_analyzer.adapters import PdfTextExtractor  # noqa: E402
from esg_analyzer.eval_harness import (  # noqa: E402
    load_manifest,
    run_eval,
    format_report,
)

DEFAULT_MODEL = os.environ.get("ESG_EVAL_MODEL", "anthropic/claude-3.5-sonnet")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    """Thin LLMClient over OpenRouter's OpenAI-compatible Chat Completions API.

    Reads the key from OPENROUTER_API_KEY — never hardcoded, never committed.
    Lazy-imports the SDK so importing this file never requires it. Swap this class
    if you later pick a different provider — the harness only needs .complete().
    """

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
                "The eval needs the 'openai' package (OpenRouter is OpenAI-compatible): "
                "pip install openai"
            ) from exc
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise SystemExit(
                "Set OPENROUTER_API_KEY to run the eval against a live model."
            )
        self._client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=key)

    def complete(self, prompt: str, report_text: str) -> str:  # pragma: no cover - network
        self._ensure()
        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""


def main(argv: list[str]) -> int:
    manifest = argv[1] if len(argv) > 1 else str(Path(__file__).parent / "golden.json")
    base_dir = Path(manifest).resolve().parent

    cases = load_manifest(manifest)
    if not cases:
        print("No cases in manifest.")
        return 1

    print(f"Running {len(cases)} golden case(s) with model {DEFAULT_MODEL}...\n")
    report = run_eval(cases, PdfTextExtractor(), OpenRouterClient(), base_dir=base_dir)
    print(format_report(report))

    # Non-zero exit if labels don't fully agree — makes the eval a CI gate later.
    return 0 if report.label_accuracy == 1.0 else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
