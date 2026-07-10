"""The analyzer pipeline orchestrator.

Wires the stages and enforces the four failure states locked in eng review.
Pure orchestration over injected edge adapters — no third-party imports, no
network. The batch runner and the eval supply real adapters; tests supply fakes.

    source
      │
      ▼  extractor.extract()          ExtractionError / too-short  ─▶ EXTRACTION_FAILED
    text ──────────────────────────────────────────────────────────────────┐
      │                                                                      │
      ▼  rubric.scan_tier1(FULL text)  ← omission tells, whole document      │
    tier1_findings                                                           │
      │                                                                      │
      ▼  prefilter() ─▶ prompt() ─▶ llm.complete()                           │
      │       parse+schema.validate  (malformed ─▶ retry once ─▶ ANALYSIS_FAILED)
      ▼  quote_gate.verify_quotes(FULL text)   ← drop non-verbatim           │
    tier2_findings                                                           │
      │                                                                      │
      ▼  combine ─▶ rubric.compute_label()                                   │
    label  (zero surviving findings AND quotes were dropped ─▶ INSUFFICIENT_DATA)
      │                                                                      │
      ▼                                                                      │
    Verdict ◀────────────────────────────────────────────────────────────────┘

Per-report isolation: analyze_report never raises for report-specific problems;
it returns a Verdict in a failure state. Only a programmer error would propagate.
"""

from __future__ import annotations

import hashlib

from .adapters import TextExtractor, LLMClient, ExtractionError
from .models import Verdict, VerdictState
from .rubric import scan_tier1, compute_label
from .prefilter import prefilter
from .prompt import build_prompt
from .schema import validate_llm_payload, SchemaError
from .quote_gate import verify_quotes

# Below this many non-whitespace chars, the extraction is treated as failed
# (scanned-image PDF, bad encoding, near-empty). Conservative floor.
MIN_TEXT_CHARS = 500


def source_hash(text: str) -> str:
    """Stable content hash of the source text — drives incremental batch dedup."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_json(raw: str):
    import json

    return json.loads(raw)


def _run_tier2(
    llm: LLMClient,
    full_text: str,
) -> tuple[list, bool]:
    """Run the Tier-2 LLM pass with one retry on malformed output.

    Returns (normalized_findings, ok). ok=False means the LLM output could not
    be validated after a retry -> caller maps to ANALYSIS_FAILED.
    If there's no claim signal to send, returns ([], True) — nothing to check.
    """
    filtered = prefilter(full_text)
    if not filtered.strip():
        return [], True

    prompt = build_prompt(filtered)

    last_err: Exception | None = None
    for _attempt in range(2):  # initial + one retry
        try:
            raw = llm.complete(prompt, filtered)
            payload = _parse_json(raw)
            return validate_llm_payload(payload), True
        except (SchemaError, ValueError) as exc:
            # ValueError covers json.JSONDecodeError (malformed JSON).
            last_err = exc
            continue

    # Both attempts failed schema/parse validation.
    assert last_err is not None
    return [], False


def analyze_report(
    company: str,
    source: str,
    extractor: TextExtractor,
    llm: LLMClient,
) -> Verdict:
    """Analyze one report end to end. Never raises for report-specific failures."""

    # --- Stage 1: ingest + extraction guard --------------------------------
    try:
        text = extractor.extract(source)
    except ExtractionError as exc:
        return Verdict(company, VerdictState.EXTRACTION_FAILED, notes=str(exc))

    stripped = "".join(text.split())
    if len(stripped) < MIN_TEXT_CHARS:
        return Verdict(
            company,
            VerdictState.EXTRACTION_FAILED,
            source_hash=source_hash(text),
            notes=(
                f"extracted text too short ({len(stripped)} non-whitespace chars "
                f"< {MIN_TEXT_CHARS}); likely scanned-image or empty PDF"
            ),
        )

    shash = source_hash(text)

    # --- Stage 2: Tier-1 omission scan over the FULL document --------------
    tier1_findings = scan_tier1(text)

    # --- Stage 3: Tier-2 LLM pass (filtered), schema-validated -------------
    llm_findings, ok = _run_tier2(llm, text)
    if not ok:
        return Verdict(
            company,
            VerdictState.ANALYSIS_FAILED,
            findings=tier1_findings,
            source_hash=shash,
            notes="LLM output failed schema validation after one retry",
        )

    # --- Stage 4: verbatim-quote gate over the FULL source text ------------
    gate = verify_quotes(llm_findings, text)
    tier2_findings = gate.kept

    findings = tier1_findings + tier2_findings

    # --- Stage 5: label / insufficient-data --------------------------------
    if not findings:
        # No findings at all. Distinguish "clean report" from "we dropped
        # everything / had nothing to judge": if the LLM proposed quotes that all
        # got dropped, that's not evidence of cleanliness — it's insufficient data.
        if gate.any_dropped:
            return Verdict(
                company,
                VerdictState.INSUFFICIENT_DATA,
                source_hash=shash,
                notes="all proposed quotes failed verbatim verification; nothing to assess",
            )
        return Verdict(
            company,
            VerdictState.RECOMMENDED,
            source_hash=shash,
            notes="no greenwashing tells found in this report",
        )

    label = compute_label(findings)
    return Verdict(
        company,
        VerdictState.from_label(label),
        findings=findings,
        source_hash=shash,
    )
