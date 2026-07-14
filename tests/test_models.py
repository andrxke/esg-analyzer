"""Tests for the data models: serialization, publishability, and label mapping.

These will be the contract the SQLite store and SSG build depend on.
"""

from __future__ import annotations

import unittest

from esg_analyzer.models import (
    Severity,
    Tier,
    Label,
    VerdictState,
    Finding,
    Verdict,
)


class TestFindingSerialization(unittest.TestCase):
    def test_to_dict_round_trip(self):
        f = Finding(
            tell_id="T3",
            severity=Severity.MAJOR,
            tier=Tier.TIER2,
            rationale="neutrality via offsets",
            quote="carbon neutral today",
        )
        d = f.to_dict()
        self.assertEqual(d["tell_id"], "T3")
        self.assertEqual(d["severity"], "major")
        self.assertEqual(d["tier"], "tier2")
        self.assertEqual(d["rationale"], "neutrality via offsets")
        self.assertEqual(d["quote"], "carbon neutral today")

    def test_to_dict_tier1_no_quote(self):
        """Tier-1 findings have no quote (empty string)."""
        f = Finding("T2", Severity.MAJOR, Tier.TIER1, "Scope 3 missing")
        d = f.to_dict()
        self.assertEqual(d["quote"], "")
        self.assertEqual(d["tier"], "tier1")

    def test_finding_is_frozen(self):
        f = Finding("T1", Severity.MAJOR, Tier.TIER2, "r", "q")
        with self.assertRaises(AttributeError):
            f.tell_id = "T99"  # type: ignore[misc]


class TestVerdictSerialization(unittest.TestCase):
    def test_to_dict_with_findings(self):
        v = Verdict(
            company="Acme",
            state=VerdictState.NOT_RECOMMENDED,
            findings=[
                Finding("T1", Severity.MAJOR, Tier.TIER2, "no baseline", "q1"),
                Finding("T3", Severity.MAJOR, Tier.TIER2, "offsets", "q2"),
            ],
            source_hash="abc123",
            notes="test",
        )
        d = v.to_dict()
        self.assertEqual(d["company"], "Acme")
        self.assertEqual(d["state"], "Not Recommended")
        self.assertEqual(d["label"], "Not Recommended")
        self.assertEqual(d["source_hash"], "abc123")
        self.assertEqual(d["notes"], "test")
        self.assertEqual(len(d["findings"]), 2)

    def test_to_dict_failure_state_label_is_none(self):
        v = Verdict("Acme", VerdictState.EXTRACTION_FAILED)
        d = v.to_dict()
        self.assertIsNone(d["label"])
        self.assertEqual(d["state"], "extraction-failed")

    def test_to_dict_empty_findings(self):
        v = Verdict("Acme", VerdictState.RECOMMENDED)
        d = v.to_dict()
        self.assertEqual(d["findings"], [])

    def test_major_minor_counts(self):
        v = Verdict(
            "Acme",
            VerdictState.NOT_RECOMMENDED,
            findings=[
                Finding("T1", Severity.MAJOR, Tier.TIER2, "r", "q"),
                Finding("T2", Severity.MAJOR, Tier.TIER1, "r"),
                Finding("T5", Severity.MINOR, Tier.TIER2, "r", "q"),
            ],
        )
        self.assertEqual(v.major_count(), 2)
        self.assertEqual(v.minor_count(), 1)


class TestVerdictPublishability(unittest.TestCase):
    """Every VerdictState must have a correct is_publishable value — this gates
    what reaches public pages in the SSG build."""

    PUBLISHABLE = {
        VerdictState.RECOMMENDED,
        VerdictState.IMPROVING,
        VerdictState.NOT_RECOMMENDED,
    }
    NOT_PUBLISHABLE = {
        VerdictState.INSUFFICIENT_DATA,
        VerdictState.EXTRACTION_FAILED,
        VerdictState.ANALYSIS_FAILED,
    }

    def test_publishable_states(self):
        for state in self.PUBLISHABLE:
            with self.subTest(state=state):
                v = Verdict("X", state)
                self.assertTrue(v.is_publishable, f"{state} should be publishable")

    def test_not_publishable_states(self):
        for state in self.NOT_PUBLISHABLE:
            with self.subTest(state=state):
                v = Verdict("X", state)
                self.assertFalse(v.is_publishable, f"{state} should NOT be publishable")

    def test_all_states_covered(self):
        """Every member of VerdictState is in exactly one group."""
        all_states = set(VerdictState)
        covered = self.PUBLISHABLE | self.NOT_PUBLISHABLE
        self.assertEqual(all_states, covered, "Not all VerdictState members are tested")


class TestVerdictLabel(unittest.TestCase):
    def test_label_for_publishable_states(self):
        self.assertEqual(Verdict("X", VerdictState.RECOMMENDED).label, Label.RECOMMENDED)
        self.assertEqual(Verdict("X", VerdictState.IMPROVING).label, Label.IMPROVING)
        self.assertEqual(Verdict("X", VerdictState.NOT_RECOMMENDED).label, Label.NOT_RECOMMENDED)

    def test_label_none_for_failure_states(self):
        self.assertIsNone(Verdict("X", VerdictState.EXTRACTION_FAILED).label)
        self.assertIsNone(Verdict("X", VerdictState.ANALYSIS_FAILED).label)
        self.assertIsNone(Verdict("X", VerdictState.INSUFFICIENT_DATA).label)


class TestVerdictStateFromLabel(unittest.TestCase):
    def test_from_label_recommended(self):
        self.assertEqual(VerdictState.from_label(Label.RECOMMENDED), VerdictState.RECOMMENDED)

    def test_from_label_improving(self):
        self.assertEqual(VerdictState.from_label(Label.IMPROVING), VerdictState.IMPROVING)

    def test_from_label_not_recommended(self):
        self.assertEqual(VerdictState.from_label(Label.NOT_RECOMMENDED), VerdictState.NOT_RECOMMENDED)


if __name__ == "__main__":
    unittest.main()
