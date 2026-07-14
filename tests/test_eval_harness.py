"""Tests for the golden-set eval harness. Stdlib unittest, fakes, no network.

Covers: label match/mismatch scoring, tell recall (found/missed/extra), token
estimate, truncation flag, manifest loading + validation, and an end-to-end run
of the committed synthetic golden set through the REAL pipeline with a fake LLM.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from esg_analyzer.eval_harness import (
    GoldenCase,
    load_manifest,
    run_eval,
    format_report,
)
from esg_analyzer.prefilter import DEFAULT_CHAR_BUDGET

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = REPO_ROOT / "eval"


class FakeExtractor:
    """Maps a source path to canned text (keyed by basename)."""

    def __init__(self, by_name):
        self._by_name = by_name

    def extract(self, source: str) -> str:
        return self._by_name[Path(source).name]


class FakeLLM:
    """Returns a fixed payload for every call (findings keyed by nothing — same each time)."""

    def __init__(self, findings=None):
        self._findings = findings or []

    def complete(self, prompt: str, report_text: str) -> str:
        return json.dumps({"findings": self._findings})


LONG = "We disclose emissions and targets transparently. " * 40  # clears MIN_TEXT_CHARS


class TestManifestLoading(unittest.TestCase):
    def test_loads_committed_golden(self):
        cases = load_manifest(EVAL_DIR / "golden.json")
        self.assertGreaterEqual(len(cases), 2)
        self.assertTrue(all(isinstance(c, GoldenCase) for c in cases))

    def test_rejects_unknown_expected_state(self):
        p = EVAL_DIR / "_bad_manifest_tmp.json"
        p.write_text(json.dumps([
            {"company": "X", "source": "s.txt", "expected_state": "Amazing"}
        ]), encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                load_manifest(p)
        finally:
            p.unlink()

    def test_rejects_non_list(self):
        p = EVAL_DIR / "_bad_manifest_tmp2.json"
        p.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                load_manifest(p)
        finally:
            p.unlink()


class TestScoring(unittest.TestCase):
    def test_label_match_and_recall(self):
        cases = [GoldenCase("Co", "r.txt", "Recommended", expected_tells=[])]
        ext = FakeExtractor({"r.txt": LONG})
        report = run_eval(cases, ext, FakeLLM([]), base_dir=".")
        r = report.results[0]
        self.assertTrue(r.label_match)
        self.assertEqual(r.recall, 1.0)
        self.assertEqual(report.label_accuracy, 1.0)

    def test_label_mismatch_detected(self):
        # Human says Not Recommended; pipeline with no findings says Recommended.
        cases = [GoldenCase("Co", "r.txt", "Not Recommended", expected_tells=["T3"])]
        ext = FakeExtractor({"r.txt": LONG})
        report = run_eval(cases, ext, FakeLLM([]), base_dir=".")
        r = report.results[0]
        self.assertFalse(r.label_match)
        self.assertEqual(r.tells_missed, ["T3"])
        self.assertEqual(r.recall, 0.0)

    def test_extra_tell_flagged(self):
        # Tier-1 will fire T2 (Scope 1/2 disclosed, Scope 3 absent) though human expected none.
        text = "Scope 1: 10,000 tCO2e. Scope 2: 5,000 tCO2e. " + LONG
        cases = [GoldenCase("Co", "r.txt", "Not Recommended", expected_tells=[])]
        ext = FakeExtractor({"r.txt": text})
        report = run_eval(cases, ext, FakeLLM([]), base_dir=".")
        r = report.results[0]
        self.assertIn("T2", r.tells_extra)

    def test_truncation_flag(self):
        # Build claim-signal content exceeding the budget -> truncated=True.
        big = ("We commit to a net-zero target by 2050. " * 5000)
        self.assertGreater(len(big), DEFAULT_CHAR_BUDGET)
        cases = [GoldenCase("Co", "r.txt", "Improving", expected_tells=[])]
        ext = FakeExtractor({"r.txt": big})
        report = run_eval(cases, ext, FakeLLM([]), base_dir=".")
        self.assertTrue(report.results[0].truncated)
        self.assertIn("Co", report.truncated_cases)


class TestGoldenSetEndToEnd(unittest.TestCase):
    """Run the committed synthetic golden set through the REAL pipeline.

    The fake LLM stands in for the Tier-2 pass by returning the quotes a correct
    model would extract (verbatim from the fixtures). This proves the harness +
    pipeline + rubric agree with the hand-labeled answer key end to end, without
    a network call. The real run (eval/run_eval.py) swaps in a live model.
    """

    def _llm_for(self, company: str):
        # Verbatim quotes copied from eval/samples/*.txt.
        if "GreenWash" in company:
            return FakeLLM([
                {"tell_id": "T3",
                 "quote": "carbon neutral today, achieved\nprimarily through the purchase of high-quality carbon offsets",
                 "rationale": "neutrality via offsets"},
                {"tell_id": "T1",
                 "quote": "made\nsignificant reductions in our environmental footprint",
                 "rationale": "reduction claim with no baseline"},
                {"tell_id": "T5",
                 "quote": "industry-leading, world-class leader",
                 "rationale": "bare superlative"},
            ])
        if "Middling" in company:
            # Verbatim from middling_corp.txt — the one unbaselined claim.
            return FakeLLM([
                {"tell_id": "T1",
                 "quote": "significant reductions in our environmental footprint",
                 "rationale": "reduction claim with no baseline value or year"},
            ])
        if "Boundary" in company:
            # Verbatim from boundary_ltd.txt — bare superlatives.
            return FakeLLM([
                {"tell_id": "T5",
                 "quote": "among the greenest companies in our industry,\ndelivering world-class performance across every dimension of sustainability",
                 "rationale": "bare superlative with no quantification"},
            ])
        return FakeLLM([])  # Solid Co. — clean

    def test_greenwash_co_not_recommended(self):
        cases = [c for c in load_manifest(EVAL_DIR / "golden.json") if "GreenWash" in c.company]
        from esg_analyzer.adapters import PdfTextExtractor
        report = run_eval(cases, PdfTextExtractor(), self._llm_for("GreenWash"), base_dir=EVAL_DIR)
        r = report.results[0]
        self.assertEqual(r.actual_state, "Not Recommended")
        self.assertTrue(r.label_match)

    def test_solid_co_recommended(self):
        cases = [c for c in load_manifest(EVAL_DIR / "golden.json") if "Solid" in c.company]
        from esg_analyzer.adapters import PdfTextExtractor
        report = run_eval(cases, PdfTextExtractor(), self._llm_for("Solid"), base_dir=EVAL_DIR)
        r = report.results[0]
        self.assertEqual(r.actual_state, "Recommended")
        self.assertTrue(r.label_match)

    def test_middling_corp_improving(self):
        """Middling Corp: 1 major tell (T1) -> Improving."""
        cases = [c for c in load_manifest(EVAL_DIR / "golden.json") if "Middling" in c.company]
        from esg_analyzer.adapters import PdfTextExtractor
        report = run_eval(cases, PdfTextExtractor(), self._llm_for("Middling"), base_dir=EVAL_DIR)
        r = report.results[0]
        self.assertEqual(r.actual_state, "Improving")
        self.assertTrue(r.label_match)

    def test_boundary_ltd_recommended(self):
        """BoundaryCase Ltd: 1 minor tell (T5) -> Recommended."""
        cases = [c for c in load_manifest(EVAL_DIR / "golden.json") if "Boundary" in c.company]
        from esg_analyzer.adapters import PdfTextExtractor
        report = run_eval(cases, PdfTextExtractor(), self._llm_for("Boundary"), base_dir=EVAL_DIR)
        r = report.results[0]
        self.assertEqual(r.actual_state, "Recommended")
        self.assertTrue(r.label_match)

    def test_format_report_runs(self):
        cases = load_manifest(EVAL_DIR / "golden.json")
        from esg_analyzer.adapters import PdfTextExtractor

        # Route each case to the right fake via a dispatching client.
        class Dispatch:
            def __init__(self, outer):
                self.outer = outer
            def complete(self, prompt, report_text):
                # Detect fixture by unique phrases in the report text.
                if "world-class leader" in report_text:
                    company = "GreenWash"
                elif "significant reductions in our environmental footprint" in report_text and "world-class" not in report_text:
                    company = "Middling"
                elif "among the greenest" in report_text:
                    company = "Boundary"
                else:
                    company = "Solid"
                return self.outer._llm_for(company).complete(prompt, report_text)

        report = run_eval(cases, PdfTextExtractor(), Dispatch(self), base_dir=EVAL_DIR)
        out = format_report(report)
        self.assertIn("GOLDEN-SET EVAL", out)
        self.assertIn("Label accuracy", out)


if __name__ == "__main__":
    unittest.main()
