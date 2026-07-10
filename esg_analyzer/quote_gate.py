"""Verbatim-quote verification gate — the legal spine.

The whole legal-safety posture is "we only ever show the company's own words."
The LLM is asked to quote verbatim, but an LLM will sometimes paraphrase, merge
sentences, or fabricate a plausible-sounding quote. This gate makes the premise
TRUE instead of hoped-for: every quote a finding carries must be an exact
substring of the extracted source text, or the finding is dropped.

Deterministic. The LLM proposes; this code verifies against the source of truth.

Whitespace handling: PDF text extraction mangles whitespace (hard line breaks
mid-sentence, runs of spaces, non-breaking spaces). A naive exact-match would
false-reject real quotes. So we normalize whitespace on BOTH sides (collapse any
run of whitespace to a single space, strip ends) before the substring check.
Case is NOT normalized — case is meaningful and a real quote preserves it.

Two other defenses live here:
- Any tell_id the LLM proposes that is not in the rubric's allow-list (a
  hallucinated id, or a deferred tell like T6) is dropped.
- Severity comes from the rubric keyed by tell_id, never from the LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Finding, Tier
from .rubric import TELLS, LLM_PROPOSABLE_TELLS

_WS_RE = re.compile(r"\s+")


def _normalize_ws(s: str) -> str:
    """Collapse all whitespace runs to a single space and strip ends."""
    return _WS_RE.sub(" ", s).strip()


@dataclass
class DroppedFinding:
    tell_id: str
    quote: str
    reason: str  # "quote-not-in-source" | "unknown-or-deferred-tell"


@dataclass
class GateResult:
    kept: list[Finding]
    dropped: list[DroppedFinding]

    @property
    def any_dropped(self) -> bool:
        return len(self.dropped) > 0


def verify_quotes(
    llm_findings: list[dict[str, str]],
    source_text: str,
) -> GateResult:
    """Verify each proposed Tier-2 finding's quote against the source.

    `llm_findings` are the normalized dicts from schema.validate_llm_payload
    (keys: tell_id, quote, rationale). Returns kept Finding objects (severity/tier
    filled from the rubric) and a list of what was dropped and why.
    """
    normalized_source = _normalize_ws(source_text)
    kept: list[Finding] = []
    dropped: list[DroppedFinding] = []

    for item in llm_findings:
        tell_id = item["tell_id"]
        quote = item["quote"]
        rationale = item["rationale"]

        tell = TELLS.get(tell_id)
        if tell is None or tell_id not in LLM_PROPOSABLE_TELLS:
            # Hallucinated id, or a tell the LLM must not propose in v1 (e.g. deferred T6).
            dropped.append(
                DroppedFinding(tell_id, quote, "unknown-or-deferred-tell")
            )
            continue

        if _normalize_ws(quote) not in normalized_source:
            # The quote is not verbatim in the source — could be fabricated or
            # paraphrased. Drop it; a verdict never carries an unverifiable quote.
            dropped.append(
                DroppedFinding(tell_id, quote, "quote-not-in-source")
            )
            continue

        kept.append(
            Finding(
                tell_id=tell_id,
                severity=tell.severity,
                tier=Tier.TIER2,
                rationale=rationale,
                quote=quote,
            )
        )

    return GateResult(kept=kept, dropped=dropped)
