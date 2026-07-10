"""Golden-set eval harness — guards label QUALITY, not just plumbing.

Unit tests (with a fake LLM) prove the pipeline wires together. They cannot prove
the prompt actually produces correct labels on real reports, and a prompt tweak
can silently wreck verdict quality with every unit test still green. This harness
closes that gap: it runs a curated set of real reports (each with a human-assigned
expected label + expected tells) through the real pipeline and scores agreement.

It also doubles as the cost-validation harness from DESIGN.md Next-Step #3:
measure real filtered token counts against the ~15-30k budget on the same reports.

Two axes, reported separately:

  LABEL QUALITY   did the tool's label match the human's?  (the trust metric)
  TELL RECALL     of the tells the human marked, how many did the tool find?
  COST            estimated Tier-2 input tokens; flag truncation (lost signal)

No network here — the caller injects the extractor + LLM. The CLI runner
(eval/run_eval.py) wires a real provider; this module stays testable with fakes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .adapters import TextExtractor, LLMClient
from .models import VerdictState, Verdict
from .prefilter import prefilter, filtered_size, DEFAULT_CHAR_BUDGET
from .pipeline import analyze_report

# Same 4-chars/token heuristic the prefilter budget assumes.
CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class GoldenCase:
    """One hand-labeled report in the golden set.

    company        display name.
    source         path to the report file (PDF/txt), relative to the manifest.
    expected_state the human-assigned VerdictState value (the answer key).
    expected_tells tell ids the human expects to fire (for recall scoring).
    note           optional: why the human judged it this way.
    """

    company: str
    source: str
    expected_state: str
    expected_tells: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class CaseResult:
    company: str
    expected_state: str
    actual_state: str
    label_match: bool
    expected_tells: list[str]
    actual_tells: list[str]
    tells_found: list[str]      # expected ∩ actual (true positives)
    tells_missed: list[str]     # expected − actual (false negatives)
    tells_extra: list[str]      # actual − expected (false positives)
    est_input_tokens: int
    truncated: bool             # claim-signal content exceeded the budget

    @property
    def recall(self) -> float:
        if not self.expected_tells:
            return 1.0
        return len(self.tells_found) / len(self.expected_tells)


@dataclass
class EvalReport:
    results: list[CaseResult]

    @property
    def label_accuracy(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.label_match) / len(self.results)

    @property
    def mean_recall(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.recall for r in self.results) / len(self.results)

    @property
    def max_tokens(self) -> int:
        return max((r.est_input_tokens for r in self.results), default=0)

    @property
    def truncated_cases(self) -> list[str]:
        return [r.company for r in self.results if r.truncated]


def load_manifest(path: str | Path) -> list[GoldenCase]:
    """Load a golden-set manifest (JSON list of case objects)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("manifest must be a JSON list of cases")
    cases = []
    for i, raw in enumerate(data):
        try:
            cases.append(
                GoldenCase(
                    company=raw["company"],
                    source=raw["source"],
                    expected_state=raw["expected_state"],
                    expected_tells=raw.get("expected_tells", []),
                    note=raw.get("note", ""),
                )
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"manifest case {i} is malformed: {exc}") from exc
    # Validate expected_state values against the enum up front — a typo in the
    # answer key would silently score every case as a mismatch otherwise.
    valid = {s.value for s in VerdictState}
    for c in cases:
        if c.expected_state not in valid:
            raise ValueError(
                f"case {c.company!r} has unknown expected_state {c.expected_state!r}; "
                f"must be one of {sorted(valid)}"
            )
    return cases


def _score_case(case: GoldenCase, verdict: Verdict, extracted_text: str) -> CaseResult:
    actual_tells = sorted({f.tell_id for f in verdict.findings})
    expected = set(case.expected_tells)
    actual = set(actual_tells)

    signal_chars = filtered_size(extracted_text)
    # Estimate tokens from what actually gets sent (capped), and detect truncation
    # from whether the uncapped signal exceeded the budget.
    sent_chars = len(prefilter(extracted_text))
    est_tokens = sent_chars // CHARS_PER_TOKEN

    return CaseResult(
        company=case.company,
        expected_state=case.expected_state,
        actual_state=verdict.state.value,
        label_match=(verdict.state.value == case.expected_state),
        expected_tells=sorted(expected),
        actual_tells=actual_tells,
        tells_found=sorted(expected & actual),
        tells_missed=sorted(expected - actual),
        tells_extra=sorted(actual - expected),
        est_input_tokens=est_tokens,
        truncated=signal_chars > DEFAULT_CHAR_BUDGET,
    )


def run_eval(
    cases: list[GoldenCase],
    extractor: TextExtractor,
    llm: LLMClient,
    base_dir: str | Path = ".",
) -> EvalReport:
    """Run every golden case through the real pipeline and score it."""
    base = Path(base_dir)
    results: list[CaseResult] = []
    for case in cases:
        source_path = str(base / case.source)
        # Extract once here so we can measure token cost on the same text the
        # pipeline sees. The pipeline re-extracts, which is fine — extraction is
        # cheap and deterministic; only the LLM call costs money.
        extracted = extractor.extract(source_path)
        verdict = analyze_report(case.company, source_path, extractor, llm)
        results.append(_score_case(case, verdict, extracted))
    return EvalReport(results=results)


def format_report(report: EvalReport, budget_tokens: int = DEFAULT_CHAR_BUDGET // CHARS_PER_TOKEN) -> str:
    """Human-readable eval summary."""
    lines: list[str] = []
    lines.append("=" * 68)
    lines.append("GOLDEN-SET EVAL")
    lines.append("=" * 68)
    for r in report.results:
        mark = "OK " if r.label_match else "XX "
        lines.append(
            f"{mark}{r.company:<24} expected={r.expected_state:<16} got={r.actual_state}"
        )
        if r.tells_missed:
            lines.append(f"     missed tells: {', '.join(r.tells_missed)}")
        if r.tells_extra:
            lines.append(f"     extra  tells: {', '.join(r.tells_extra)}")
        flag = "  ⚠ TRUNCATED (lost signal)" if r.truncated else ""
        lines.append(f"     ~{r.est_input_tokens} input tokens{flag}")
    lines.append("-" * 68)
    lines.append(
        f"Label accuracy: {report.label_accuracy:.0%}  "
        f"|  Mean tell recall: {report.mean_recall:.0%}  "
        f"|  Max tokens: {report.max_tokens} (budget {budget_tokens})"
    )
    if report.truncated_cases:
        lines.append(f"⚠ Truncated (revisit cost model): {', '.join(report.truncated_cases)}")
    if report.max_tokens > budget_tokens:
        lines.append("⚠ A case exceeded the token budget — the cost model needs revisiting.")
    lines.append("=" * 68)
    return "\n".join(lines)
