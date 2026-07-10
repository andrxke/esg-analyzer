"""The tells rubric, encoded as code. Source of truth: ../docs/rubric.md.

Two responsibilities:

1. TELLS — the fixed catalog (id -> severity, tier, description). The LLM
   proposes which tell fired by id; severity/tier come from HERE, never the LLM.

2. Label logic — a pure function of severity counts (moderate strictness,
   locked 2026-07-10). Minor tells alone can never reach Not Recommended.

3. Tier-1 presence scanners — cheap regex/keyword scans over the WHOLE report
   for the omission tells (you cannot detect an omission from a filtered
   excerpt). No LLM. Conservative by design: only fire on clear signals.

    label decision (severity-driven, NOT count):
      major >= 2                      -> NOT_RECOMMENDED
      major == 1                      -> IMPROVING
      major == 0 and minor >= 2       -> IMPROVING
      major == 0 and minor <= 1       -> RECOMMENDED
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Severity, Tier, Label, Finding


@dataclass(frozen=True)
class Tell:
    tell_id: str
    name: str
    severity: Severity
    tier: Tier
    deferred: bool = False  # T6 goalpost — defined for completeness, not run in v1


# The catalog. Keyed by id for O(1) lookup when the LLM references a tell.
TELLS: dict[str, Tell] = {
    "T1": Tell("T1", "Unbaselined headline claim", Severity.MAJOR, Tier.TIER2),
    "T2": Tell("T2", "Missing or unquantified Scope 3", Severity.MAJOR, Tier.TIER1),
    "T3": Tell("T3", "Offset-dependent neutrality", Severity.MAJOR, Tier.TIER2),
    "T4": Tell("T4", "Long-dated target, no interim milestones", Severity.MINOR, Tier.TIER1),
    "T5": Tell("T5", "Vague superlative, no number", Severity.MINOR, Tier.TIER2),
    "T6": Tell("T6", "Goalpost shifting", Severity.MAJOR, Tier.TIER2, deferred=True),
}

# Tells the Tier-2 LLM pass is allowed to propose in v1 (presence tells only,
# T6 deferred). Used to reject unknown/deferred ids the model might hallucinate.
LLM_PROPOSABLE_TELLS = {"T1", "T3", "T5"}


def severity_of(tell_id: str) -> Severity | None:
    tell = TELLS.get(tell_id)
    return tell.severity if tell else None


def compute_label(findings: list[Finding]) -> Label:
    """Severity-driven label (moderate strictness). Pure function of the counts."""
    major = sum(1 for f in findings if f.severity is Severity.MAJOR)
    minor = sum(1 for f in findings if f.severity is Severity.MINOR)

    if major >= 2:
        return Label.NOT_RECOMMENDED
    if major == 1:
        return Label.IMPROVING
    if minor >= 2:
        return Label.IMPROVING
    return Label.RECOMMENDED


# --------------------------------------------------------------------------
# Tier-1 presence scanners — whole-document, no LLM.
# --------------------------------------------------------------------------

# Match "Scope 3" / "Scope-3" / "scope3", case-insensitive.
_SCOPE3_RE = re.compile(r"\bscope[\s\-]?3\b", re.IGNORECASE)
_SCOPE12_RE = re.compile(r"\bscope[\s\-]?[12]\b", re.IGNORECASE)
# A tonnage figure near an emissions term: e.g. "12,000 tCO2e", "1.2 MtCO2e".
_TONNAGE_RE = re.compile(
    r"\d[\d,\.]*\s*(?:kt|mt|t)?\s*co2(?:e|-?eq(?:uivalent)?)?",
    re.IGNORECASE,
)
# Target years far out (2040-2060). Interim milestone years (2025-2039).
_LONG_TARGET_RE = re.compile(r"\b(?:20[4-6]\d)\b")
_INTERIM_YEAR_RE = re.compile(r"\b(?:202[5-9]|203\d)\b")
_NETZERO_RE = re.compile(r"\bnet[\s\-]?zero\b|\bcarbon\s+neutral(?:ity)?\b", re.IGNORECASE)


def _tonnage_follows(text: str, match: re.Match, radius: int = 80) -> bool:
    """Is there a CO2e tonnage figure just AFTER a match?

    Forward-only and small: a quantified scope reads "Scope 3: 120,000 tCO2e",
    with the figure immediately after the label. Looking backward too (or with a
    wide window) would catch a neighboring scope's figure — e.g. a preceding
    "Scope 2: 5,000 tCO2e" — and wrongly conclude Scope 3 is quantified.
    """
    start = match.start()
    end = min(len(text), match.end() + radius)
    return _TONNAGE_RE.search(text[start:end]) is not None


def scan_tier1(text: str) -> list[Finding]:
    """Run all Tier-1 (omission) scanners over the full report text.

    Conservative: each scanner fires only on a clear, defensible signal, because
    a Tier-1 finding is computed against the whole document and stands on its own
    (no quote to verify later).
    """
    findings: list[Finding] = []

    t2 = _scan_missing_scope3(text)
    if t2:
        findings.append(t2)

    t4 = _scan_no_interim_milestones(text)
    if t4:
        findings.append(t4)

    return findings


def _scan_missing_scope3(text: str) -> Finding | None:
    """T2: report discloses Scope 1/2 emissions but Scope 3 is absent or unquantified.

    Only fires when Scope 1/2 emissions are actually disclosed (a real emissions
    inventory exists) — otherwise absence of Scope 3 isn't a tell, the report just
    isn't an emissions report.
    """
    has_scope12 = _SCOPE12_RE.search(text) is not None
    if not has_scope12:
        return None
    # Require Scope 1/2 to actually be quantified somewhere, else it's not an inventory.
    if _TONNAGE_RE.search(text) is None:
        return None

    scope3_match = _SCOPE3_RE.search(text)
    if scope3_match is None:
        return Finding(
            tell_id="T2",
            severity=Severity.MAJOR,
            tier=Tier.TIER1,
            rationale=(
                "Scope 1/2 emissions are disclosed with figures, but Scope 3 is "
                "never mentioned — the value chain (typically the majority of the "
                "footprint) is omitted entirely."
            ),
        )

    if not _tonnage_follows(text, scope3_match):
        return Finding(
            tell_id="T2",
            severity=Severity.MAJOR,
            tier=Tier.TIER1,
            rationale=(
                "Scope 3 is named but no accompanying emissions figure appears "
                "near it — mentioned without being quantified."
            ),
        )

    return None


def _scan_no_interim_milestones(text: str) -> Finding | None:
    """T4: a long-dated target (2040-2060) with no interim milestone year (2025-2039).

    Only fires when a long-dated target actually exists alongside a net-zero /
    neutrality claim — a report with no long-term target can't be shifting goalposts
    by omitting interim ones.
    """
    if _NETZERO_RE.search(text) is None:
        return None
    if _LONG_TARGET_RE.search(text) is None:
        return None
    if _INTERIM_YEAR_RE.search(text) is not None:
        return None

    return Finding(
        tell_id="T4",
        severity=Severity.MINOR,
        tier=Tier.TIER1,
        rationale=(
            "A long-dated target (2040-2060) and a net-zero/neutrality claim appear, "
            "but no interim milestone year (2025-2039) is stated — a promise with no "
            "nearer checkpoint."
        ),
    )
