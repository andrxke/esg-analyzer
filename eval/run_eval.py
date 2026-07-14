#!/usr/bin/env python3
"""CLI runner for the golden-set eval.

    python3 eval/run_eval.py                 # uses eval/golden.json
    python3 eval/run_eval.py path/to/manifest.json

The harness (esg_analyzer/eval_harness.py) stays provider-agnostic and testable
with fakes; the real network client lives in esg_analyzer/openrouter_client.py
(shared with the build-time batch). This runner just wires them together.

Provider is OpenRouter (OpenAI-compatible API). Model defaults to
`openrouter/auto` which lets OpenRouter route to the best model for the task.
Override with `ESG_EVAL_MODEL` env var to pin a specific model.

    pip install openai
    export OPENROUTER_API_KEY=sk-or-...
    python3 eval/run_eval.py

    # Pin a specific model:
    export ESG_EVAL_MODEL=anthropic/claude-3.5-sonnet
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Allow running as `python3 eval/run_eval.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from esg_analyzer.adapters import PdfTextExtractor  # noqa: E402
from esg_analyzer.openrouter_client import DEFAULT_MODEL, OpenRouterClient  # noqa: E402
from esg_analyzer.eval_harness import (  # noqa: E402
    load_manifest,
    run_eval,
    format_report,
)


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
