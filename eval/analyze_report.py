#!/usr/bin/env python3
"""Analyze a real company report and optionally add it to the golden set.

Usage:
    # Step 1: Run a report and review what the tool finds
    python3 eval/analyze_report.py "Tesla" path/to/tesla-sustainability-2024.pdf

    # Step 2: Review the output. Decide if you agree with the label.
    # The script shows every finding, the label, and quotes — so you can judge.

    # Step 3: Add it to the golden set with YOUR human judgment
    python3 eval/analyze_report.py "Tesla" path/to/tesla-sustainability-2024.pdf \
        --add-golden --expected-state "Not Recommended" --expected-tells T1 T2 T3

This is the bridge between "I have a PDF" and "it's in the golden set."
The golden set records YOUR judgment (the answer key), not the tool's output.
When you re-run the eval after a prompt change, mismatches tell you the prompt
regressed — or that you want to update your annotation.

Reports are copied into eval/samples/ so the golden set is self-contained and
reproducible.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import textwrap
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Allow running from repo root: `python3 eval/analyze_report.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from esg_analyzer.adapters import PdfTextExtractor, ExtractionError  # noqa: E402
from esg_analyzer.openrouter_client import DEFAULT_MODEL, OpenRouterClient  # noqa: E402
from esg_analyzer.pipeline import analyze_report, source_hash, MIN_TEXT_CHARS  # noqa: E402
from esg_analyzer.prefilter import prefilter, filtered_size, DEFAULT_CHAR_BUDGET  # noqa: E402
from esg_analyzer.models import VerdictState  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
GOLDEN_PATH = EVAL_DIR / "golden.json"
SAMPLES_DIR = EVAL_DIR / "samples"
CHARS_PER_TOKEN = 4


# ── Display ──────────────────────────────────────────────────────────────────

def display_verdict(verdict, extracted_text: str):
    """Print a human-readable verdict for review."""
    print("=" * 70)
    print(f"  COMPANY:  {verdict.company}")
    print(f"  LABEL:    {verdict.state.value}")
    print(f"  PUBLISH:  {'yes' if verdict.is_publishable else 'no (excluded from public pages)'}")
    print("=" * 70)

    if verdict.notes:
        print(f"\n  Notes: {verdict.notes}")

    if verdict.findings:
        print(f"\n  FINDINGS ({len(verdict.findings)}):")
        print("-" * 70)
        for i, f in enumerate(verdict.findings, 1):
            print(f"\n  [{i}] {f.tell_id} ({f.severity.value.upper()}, {f.tier.value})")
            print(f"      {f.rationale}")
            if f.quote:
                wrapped = textwrap.fill(f.quote, width=60, initial_indent="      \"",
                                        subsequent_indent="       ")
                print(f"{wrapped}\"")
        print()
    else:
        print("\n  No findings.\n")

    # Cost info
    signal_chars = filtered_size(extracted_text)
    sent_chars = len(prefilter(extracted_text))
    est_tokens = sent_chars // CHARS_PER_TOKEN
    budget_tokens = DEFAULT_CHAR_BUDGET // CHARS_PER_TOKEN
    truncated = signal_chars > DEFAULT_CHAR_BUDGET

    print("-" * 70)
    print(f"  Source hash:       {verdict.source_hash[:16]}...")
    print(f"  Extracted chars:   {len(extracted_text):,}")
    print(f"  Signal chars:      {signal_chars:,} (pre-budget)")
    print(f"  Sent to LLM:      ~{est_tokens:,} tokens (budget: {budget_tokens:,})")
    if truncated:
        print("  ⚠ TRUNCATED — signal content exceeded budget (some evidence may be lost)")
    print("=" * 70)


# ── Golden-set management ───────────────────────────────────────────────────

def load_golden() -> list[dict]:
    if GOLDEN_PATH.exists():
        return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return []


def save_golden(cases: list[dict]):
    GOLDEN_PATH.write_text(
        json.dumps(cases, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def add_to_golden(company: str, source_path: Path, expected_state: str,
                  expected_tells: list[str], note: str = ""):
    """Copy the report into eval/samples/ and add an entry to golden.json."""
    # Copy file to samples dir
    dest = SAMPLES_DIR / source_path.name
    if not dest.exists():
        SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dest)
        print(f"  Copied {source_path.name} → eval/samples/")
    else:
        print(f"  {source_path.name} already in eval/samples/")

    # Validate expected_state
    valid_states = {s.value for s in VerdictState}
    if expected_state not in valid_states:
        print(f"  ERROR: '{expected_state}' not a valid state. Must be one of:")
        for s in sorted(valid_states):
            print(f"    - {s}")
        return False

    # Add to golden.json
    cases = load_golden()
    relative_source = f"samples/{source_path.name}"

    # Check for duplicates
    for c in cases:
        if c["source"] == relative_source:
            print(f"  Already in golden.json (source: {relative_source}). Skipping.")
            return False

    cases.append({
        "company": company,
        "source": relative_source,
        "expected_state": expected_state,
        "expected_tells": expected_tells,
        "note": note,
    })
    save_golden(cases)
    print(f"  ✓ Added to golden.json: {company} → {expected_state}")
    print(f"    Expected tells: {expected_tells or '(none)'}")
    return True


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Analyze a sustainability report and optionally add to golden set.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              # Just analyze and review:
              python3 eval/analyze_report.py "Shell" reports/shell-2024.pdf

              # Analyze, then add to golden set with your human judgment:
              python3 eval/analyze_report.py "Shell" reports/shell-2024.pdf \\
                  --add-golden --expected-state "Not Recommended" --expected-tells T1 T2 T3
        """),
    )
    parser.add_argument("company", help="Company display name (e.g. 'Tesla')")
    parser.add_argument("report", help="Path to the report file (PDF or txt)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"OpenRouter model (default: {DEFAULT_MODEL})")
    parser.add_argument("--add-golden", action="store_true",
                        help="Add this report to the golden set after analysis")
    parser.add_argument("--expected-state",
                        help="YOUR human-assigned label (e.g. 'Not Recommended')")
    parser.add_argument("--expected-tells", nargs="*", default=[],
                        help="Tell IDs you expect to fire (e.g. T1 T2 T3)")
    parser.add_argument("--note", default="",
                        help="Why you judged it this way (stored in golden.json)")

    args = parser.parse_args()
    report_path = Path(args.report).resolve()

    if not report_path.exists():
        print(f"ERROR: File not found: {report_path}")
        return 1

    # ── Run the pipeline ─────────────────────────────────────────────────
    print(f"\nAnalyzing: {args.company}")
    print(f"Report:    {report_path}")
    print(f"Model:     {args.model}\n")

    extractor = PdfTextExtractor()
    llm = OpenRouterClient(model=args.model)

    try:
        extracted_text = extractor.extract(str(report_path))
    except ExtractionError as e:
        print(f"ERROR: Could not extract text: {e}")
        return 1

    verdict = analyze_report(args.company, str(report_path), extractor, llm)
    display_verdict(verdict, extracted_text)

    # ── Optionally add to golden set ─────────────────────────────────────
    if args.add_golden:
        if not args.expected_state:
            print("\nERROR: --add-golden requires --expected-state")
            print("  This is YOUR human judgment, not the tool's output.")
            print("  Example: --expected-state 'Not Recommended' --expected-tells T1 T2")
            return 1

        print()
        add_to_golden(
            company=args.company,
            source_path=report_path,
            expected_state=args.expected_state,
            expected_tells=args.expected_tells,
            note=args.note or f"Human-annotated. Tool said: {verdict.state.value}",
        )

    # ── Prompt for annotation if not adding ──────────────────────────────
    if not args.add_golden:
        print("\n  To add this to the golden set with YOUR judgment, re-run with:")
        print(f'  python3 eval/analyze_report.py "{args.company}" "{args.report}" \\')
        print(f'      --add-golden --expected-state "<your label>" --expected-tells T1 T2 ...')
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
