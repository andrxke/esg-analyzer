"""ESG greenwashing analyzer.

Reads a company's sustainability report and produces a Consumer-Reports-style
label (Recommended / Improving / Not Recommended) backed by quoted evidence.

The core logic (models, rubric, quote gate, pipeline) depends on nothing outside
the standard library. PDF extraction and the LLM client are isolated as thin edge
adapters (see `adapters.py`) so the full test suite runs with zero installs and
only the golden-set eval ever needs a real API key.

Design: ../DESIGN.md   Rubric: ../docs/rubric.md
"""

from .models import (
    Severity,
    Tier,
    Label,
    VerdictState,
    Finding,
    Verdict,
)

__all__ = [
    "Severity",
    "Tier",
    "Label",
    "VerdictState",
    "Finding",
    "Verdict",
]
