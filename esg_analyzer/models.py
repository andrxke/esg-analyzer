"""Core data models and enums for the analyzer pipeline.

Stdlib only. Everything downstream (rubric, quote gate, pipeline, storage)
speaks in these types.

Verdict states map to the four pipeline failure modes locked in eng review plus
the three real labels:

    ┌─────────────────────────── VerdictState ───────────────────────────┐
    │ real labels        │ RECOMMENDED · IMPROVING · NOT_RECOMMENDED       │
    │ non-verdict states │ INSUFFICIENT_DATA · EXTRACTION_FAILED           │
    │                    │ ANALYSIS_FAILED                                 │
    └─────────────────────────────────────────────────────────────────────┘

Only the three real labels are ever published. The other three are excluded
from public pages (see DESIGN.md "SSG build" — failed-state reports excluded).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, asdict
from typing import Any


class Severity(enum.Enum):
    """A tell's weight. Labels are a function of severity, not raw count."""

    MAJOR = "major"
    MINOR = "minor"


class Tier(enum.Enum):
    """How a tell is detected.

    TIER1 = cheap presence/absence scan over the WHOLE report (regex/keyword,
            no LLM). Correct for omission tells — you cannot detect an omission
            from a filtered excerpt.
    TIER2 = filtered LLM pass for quoted evidence on the claim/number sections.
    """

    TIER1 = "tier1"
    TIER2 = "tier2"


class Label(str, enum.Enum):
    """The three publishable labels. `str` mixin so JSON/templates render cleanly."""

    RECOMMENDED = "Recommended"
    IMPROVING = "Improving"
    NOT_RECOMMENDED = "Not Recommended"


class VerdictState(str, enum.Enum):
    """Full outcome space: the three labels plus non-verdict states.

    INSUFFICIENT_DATA never collapses to RECOMMENDED (DESIGN.md label logic):
    a clean report and a too-thin/all-quotes-dropped report are different things.
    """

    RECOMMENDED = "Recommended"
    IMPROVING = "Improving"
    NOT_RECOMMENDED = "Not Recommended"
    INSUFFICIENT_DATA = "insufficient-data"
    EXTRACTION_FAILED = "extraction-failed"
    ANALYSIS_FAILED = "analysis-failed"

    @property
    def is_publishable(self) -> bool:
        """Only real labels reach public verdict pages."""
        return self in {
            VerdictState.RECOMMENDED,
            VerdictState.IMPROVING,
            VerdictState.NOT_RECOMMENDED,
        }

    @classmethod
    def from_label(cls, label: Label) -> "VerdictState":
        return cls(label.value)


@dataclass(frozen=True)
class Finding:
    """One triggered tell with its evidence.

    tell_id     e.g. "T2" — keys into the rubric.
    severity    MAJOR / MINOR — drives the label.
    quote       verbatim text from the source (Tier-2), or "" for a pure
                Tier-1 presence/absence finding that has no quotable span.
    rationale   short human-readable explanation shown on the verdict page.
    tier        which detector produced it.
    """

    tell_id: str
    severity: Severity
    tier: Tier
    rationale: str
    quote: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tell_id": self.tell_id,
            "severity": self.severity.value,
            "tier": self.tier.value,
            "rationale": self.rationale,
            "quote": self.quote,
        }


@dataclass
class Verdict:
    """The full result of analyzing one report.

    company       display name.
    state         the outcome (label or failure/insufficient state).
    findings      the surviving findings (post quote-gate).
    source_hash   content hash of the source text — drives incremental batch
                  dedup (skip re-analysis when unchanged) and report-edition
                  provenance.
    notes         optional operator note (e.g. why a state was assigned).
    """

    company: str
    state: VerdictState
    findings: list[Finding] = field(default_factory=list)
    source_hash: str = ""
    notes: str = ""

    @property
    def label(self) -> Label | None:
        """The published label, or None for non-verdict states."""
        if self.state.is_publishable:
            return Label(self.state.value)
        return None

    @property
    def is_publishable(self) -> bool:
        return self.state.is_publishable

    def major_count(self) -> int:
        return sum(1 for f in self.findings if f.severity is Severity.MAJOR)

    def minor_count(self) -> int:
        return sum(1 for f in self.findings if f.severity is Severity.MINOR)

    def to_dict(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "state": self.state.value,
            "label": self.label.value if self.label else None,
            "source_hash": self.source_hash,
            "notes": self.notes,
            "findings": [f.to_dict() for f in self.findings],
        }
