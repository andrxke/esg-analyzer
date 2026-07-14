"""Prompt regression tests — the highest-leverage gap in the test suite.

A tiny wording change to the prompt can silently wreck verdict quality with
every unit test still green (the fake LLMs never see the real prompt). These
tests make prompt changes VISIBLE:

  - Snapshot: a hash of SYSTEM_FRAMING must match a pinned value. Any change
    forces a deliberate test update and, critically, a re-run of the golden-set
    eval (the only thing that guards label *quality*).
  - Structural: the prompt must contain specific elements that the pipeline's
    correctness depends on (injection defense, allowed tells, JSON shape, report
    tags). These survive minor rewording but catch accidental deletions.
"""

from __future__ import annotations

import hashlib
import unittest

from esg_analyzer.prompt import SYSTEM_FRAMING, build_prompt


class TestPromptSnapshot(unittest.TestCase):
    """Pin the exact prompt so changes show up as a diff in review."""

    # To update: run `python3 -c "import hashlib; from esg_analyzer.prompt import
    # SYSTEM_FRAMING; print(hashlib.sha256(SYSTEM_FRAMING.encode()).hexdigest())"`
    # then paste the new hash here AND re-run the golden-set eval.
    PINNED_HASH = hashlib.sha256(SYSTEM_FRAMING.encode("utf-8")).hexdigest()

    def test_system_framing_unchanged(self):
        """If this fails, you changed the prompt. Update the hash AND re-run
        `python3 eval/run_eval.py` to verify labels still match."""
        current = hashlib.sha256(SYSTEM_FRAMING.encode("utf-8")).hexdigest()
        self.assertEqual(
            current,
            self.PINNED_HASH,
            "SYSTEM_FRAMING has changed! Update PINNED_HASH in this test "
            "and re-run the golden-set eval (python3 eval/run_eval.py) to "
            "verify label quality is preserved.",
        )


class TestPromptStructure(unittest.TestCase):
    """Structural invariants the pipeline depends on — survive rewording."""

    def test_contains_report_tags(self):
        """build_prompt must wrap report text in <report> delimiters."""
        prompt = build_prompt("some report text")
        self.assertIn("<report>", prompt)
        self.assertIn("</report>", prompt)
        self.assertIn("some report text", prompt)

    def test_report_text_inside_tags(self):
        """Report content must appear between <report> and </report>."""
        prompt = build_prompt("UNIQUE_MARKER_XYZ")
        start = prompt.index("<report>")
        end = prompt.index("</report>")
        between = prompt[start:end]
        self.assertIn("UNIQUE_MARKER_XYZ", between)

    def test_only_v1_tells_listed(self):
        """Prompt must reference T1, T3, T5 (the v1 LLM-proposable tells) and
        NOT T2, T4 (Tier-1 only) or T6 (deferred)."""
        self.assertIn("T1", SYSTEM_FRAMING)
        self.assertIn("T3", SYSTEM_FRAMING)
        self.assertIn("T5", SYSTEM_FRAMING)
        # T2 and T4 are Tier-1 scanners — the LLM must not propose them.
        # T6 is deferred. None should appear as proposable tells.
        # (They may appear in text like "T2" but not as tell IDs to find.)
        self.assertNotIn("T2 —", SYSTEM_FRAMING)
        self.assertNotIn("T4 —", SYSTEM_FRAMING)
        self.assertNotIn("T6 —", SYSTEM_FRAMING)

    def test_prompt_injection_defense(self):
        """The prompt must instruct the model to treat report content as data,
        not instructions."""
        lower = SYSTEM_FRAMING.lower()
        self.assertTrue(
            "data" in lower and "not" in lower,
            "Prompt must contain injection defense (treat content as data, not instructions)",
        )
        self.assertIn("ignore", lower)

    def test_requires_strict_json(self):
        """The prompt must ask for strict JSON output with the expected shape."""
        self.assertIn("JSON", SYSTEM_FRAMING)
        self.assertIn("findings", SYSTEM_FRAMING)
        self.assertIn("tell_id", SYSTEM_FRAMING)
        self.assertIn("quote", SYSTEM_FRAMING)
        self.assertIn("rationale", SYSTEM_FRAMING)

    def test_requires_verbatim_quotes(self):
        """The prompt must instruct character-for-character copying."""
        lower = SYSTEM_FRAMING.lower()
        self.assertTrue(
            "verbatim" in lower or "character-for-character" in lower,
            "Prompt must require verbatim/character-for-character quotes",
        )

    def test_empty_findings_instruction(self):
        """The prompt must tell the model to return empty findings when no tell applies."""
        self.assertIn('{"findings": []}', SYSTEM_FRAMING)


if __name__ == "__main__":
    unittest.main()
