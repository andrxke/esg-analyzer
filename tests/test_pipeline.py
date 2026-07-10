"""Test suite for the analyzer core. Stdlib unittest, fake adapters, no network.

Covers every path from the eng-review coverage diagram:
  - quote gate: verbatim-match keeps, non-match drops, all-dropped, unknown/deferred tell, whitespace
  - schema validation: happy + every malformed shape
  - label logic: all four severity boundaries
  - Tier-1 scanners: missing Scope 3, unquantified Scope 3, no interim milestones (+ negatives)
  - pipeline failure states: EXTRACTION_FAILED (raise + too-short), ANALYSIS_FAILED (retry then fail),
    ANALYSIS retry-succeeds, INSUFFICIENT_DATA (all quotes dropped), RECOMMENDED (clean), NOT_RECOMMENDED
  - prefilter: keeps signal blocks, respects budget, empty on no signal
  - source_hash: stable + content-sensitive (incremental batch dedup)
"""

from __future__ import annotations

import json
import unittest

from esg_analyzer.models import Severity, Tier, Label, VerdictState, Finding, Verdict
from esg_analyzer.schema import validate_llm_payload, SchemaError
from esg_analyzer.rubric import compute_label, scan_tier1
from esg_analyzer.quote_gate import verify_quotes
from esg_analyzer.prefilter import prefilter, DEFAULT_CHAR_BUDGET
from esg_analyzer.pipeline import analyze_report, source_hash, MIN_TEXT_CHARS
from esg_analyzer.adapters import ExtractionError


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

class FakeExtractor:
    def __init__(self, text=None, exc=None):
        self._text = text
        self._exc = exc

    def extract(self, source: str) -> str:
        if self._exc is not None:
            raise self._exc
        return self._text


class FakeLLM:
    """Returns queued responses in order. Records how many times it was called."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def complete(self, prompt: str, report_text: str) -> str:
        self.calls += 1
        if self._responses:
            return self._responses.pop(0)
        return json.dumps({"findings": []})


def _payload(*findings):
    return json.dumps({"findings": list(findings)})


# A body long enough to clear MIN_TEXT_CHARS, with claim signal for the prefilter.
LONG_BODY = (
    "Our sustainability report. We are industry-leading in climate action. "
    "We commit to net-zero by 2050. " + ("Additional narrative text. " * 60)
)
assert len("".join(LONG_BODY.split())) >= MIN_TEXT_CHARS


# --------------------------------------------------------------------------
# Schema validation
# --------------------------------------------------------------------------

class TestSchema(unittest.TestCase):
    def test_valid_payload_normalizes(self):
        out = validate_llm_payload(
            {"findings": [{"tell_id": " T1 ", "quote": "x", "rationale": " r "}]}
        )
        self.assertEqual(out, [{"tell_id": "T1", "quote": "x", "rationale": "r"}])

    def test_empty_findings_ok(self):
        self.assertEqual(validate_llm_payload({"findings": []}), [])

    def test_not_a_dict(self):
        with self.assertRaises(SchemaError):
            validate_llm_payload([1, 2, 3])

    def test_missing_findings_key(self):
        with self.assertRaises(SchemaError):
            validate_llm_payload({"nope": []})

    def test_findings_not_list(self):
        with self.assertRaises(SchemaError):
            validate_llm_payload({"findings": "T1"})

    def test_finding_missing_field(self):
        with self.assertRaises(SchemaError):
            validate_llm_payload({"findings": [{"tell_id": "T1", "quote": "x"}]})

    def test_finding_wrong_type(self):
        with self.assertRaises(SchemaError):
            validate_llm_payload(
                {"findings": [{"tell_id": "T1", "quote": 5, "rationale": "r"}]}
            )

    def test_finding_empty_quote(self):
        with self.assertRaises(SchemaError):
            validate_llm_payload(
                {"findings": [{"tell_id": "T1", "quote": "   ", "rationale": "r"}]}
            )


# --------------------------------------------------------------------------
# Label logic (severity-driven, moderate strictness)
# --------------------------------------------------------------------------

class TestLabelLogic(unittest.TestCase):
    def _f(self, sev):
        return Finding("T1", sev, Tier.TIER2, "r", "q")

    def test_two_major_not_recommended(self):
        self.assertEqual(
            compute_label([self._f(Severity.MAJOR), self._f(Severity.MAJOR)]),
            Label.NOT_RECOMMENDED,
        )

    def test_three_major_still_not_recommended(self):
        self.assertEqual(
            compute_label([self._f(Severity.MAJOR)] * 3), Label.NOT_RECOMMENDED
        )

    def test_one_major_improving(self):
        self.assertEqual(compute_label([self._f(Severity.MAJOR)]), Label.IMPROVING)

    def test_two_minor_improving(self):
        self.assertEqual(
            compute_label([self._f(Severity.MINOR), self._f(Severity.MINOR)]),
            Label.IMPROVING,
        )

    def test_one_minor_recommended(self):
        self.assertEqual(compute_label([self._f(Severity.MINOR)]), Label.RECOMMENDED)

    def test_zero_findings_recommended(self):
        self.assertEqual(compute_label([]), Label.RECOMMENDED)

    def test_minors_never_reach_not_recommended(self):
        # Five minor tells must still cap at Improving, never Not Recommended.
        self.assertEqual(
            compute_label([self._f(Severity.MINOR)] * 5), Label.IMPROVING
        )


# --------------------------------------------------------------------------
# Quote gate (the legal spine)
# --------------------------------------------------------------------------

class TestQuoteGate(unittest.TestCase):
    SOURCE = "We are proud to be carbon neutral today through purchased offsets."

    def test_verbatim_match_kept(self):
        res = verify_quotes(
            [{"tell_id": "T3", "quote": "carbon neutral today", "rationale": "r"}],
            self.SOURCE,
        )
        self.assertEqual(len(res.kept), 1)
        self.assertFalse(res.any_dropped)
        self.assertEqual(res.kept[0].severity, Severity.MAJOR)
        self.assertEqual(res.kept[0].tier, Tier.TIER2)

    def test_nonmatch_dropped(self):
        res = verify_quotes(
            [{"tell_id": "T3", "quote": "we invented this quote", "rationale": "r"}],
            self.SOURCE,
        )
        self.assertEqual(res.kept, [])
        self.assertEqual(res.dropped[0].reason, "quote-not-in-source")

    def test_whitespace_normalized_match(self):
        # Source has a hard line break mid-phrase (PDF artifact); quote is clean.
        source = "We are carbon\n   neutral   today."
        res = verify_quotes(
            [{"tell_id": "T3", "quote": "carbon neutral today", "rationale": "r"}],
            source,
        )
        self.assertEqual(len(res.kept), 1)

    def test_unknown_tell_dropped(self):
        res = verify_quotes(
            [{"tell_id": "T99", "quote": "carbon neutral today", "rationale": "r"}],
            self.SOURCE,
        )
        self.assertEqual(res.kept, [])
        self.assertEqual(res.dropped[0].reason, "unknown-or-deferred-tell")

    def test_deferred_tell_t6_dropped(self):
        # T6 exists in the rubric but must not be LLM-proposable in v1.
        res = verify_quotes(
            [{"tell_id": "T6", "quote": "carbon neutral today", "rationale": "r"}],
            self.SOURCE,
        )
        self.assertEqual(res.kept, [])
        self.assertEqual(res.dropped[0].reason, "unknown-or-deferred-tell")

    def test_case_sensitive(self):
        # Case is meaningful; a case-mismatched "quote" is not verbatim.
        res = verify_quotes(
            [{"tell_id": "T3", "quote": "CARBON NEUTRAL TODAY", "rationale": "r"}],
            self.SOURCE,
        )
        self.assertEqual(res.kept, [])


# --------------------------------------------------------------------------
# Tier-1 scanners
# --------------------------------------------------------------------------

class TestTier1(unittest.TestCase):
    def test_missing_scope3_fires(self):
        text = "Scope 1 emissions were 10,000 tCO2e and Scope 2 were 5,000 tCO2e."
        findings = scan_tier1(text)
        ids = {f.tell_id for f in findings}
        self.assertIn("T2", ids)

    def test_scope3_present_and_quantified_no_fire(self):
        text = (
            "Scope 1: 10,000 tCO2e. Scope 2: 5,000 tCO2e. "
            "Scope 3: 120,000 tCO2e across the value chain."
        )
        ids = {f.tell_id for f in scan_tier1(text)}
        self.assertNotIn("T2", ids)

    def test_scope3_named_but_unquantified_fires(self):
        text = (
            "Scope 1: 10,000 tCO2e. Scope 2: 5,000 tCO2e. "
            "We also recognize Scope 3 as an area for future focus and engagement "
            "with our suppliers over the coming years as our program matures further."
        )
        ids = {f.tell_id for f in scan_tier1(text)}
        self.assertIn("T2", ids)

    def test_no_emissions_inventory_no_scope3_fire(self):
        # No tonnage anywhere -> not an emissions report -> T2 must not fire.
        text = "We care about Scope 1 and Scope 2 conceptually but report no figures."
        ids = {f.tell_id for f in scan_tier1(text)}
        self.assertNotIn("T2", ids)

    def test_no_interim_milestones_fires(self):
        text = "We commit to net-zero by 2050. Our long-term vision is bold."
        ids = {f.tell_id for f in scan_tier1(text)}
        self.assertIn("T4", ids)

    def test_interim_milestone_present_no_fire(self):
        text = "We commit to net-zero by 2050, with a 50% cut by 2030."
        ids = {f.tell_id for f in scan_tier1(text)}
        self.assertNotIn("T4", ids)

    def test_no_longterm_target_no_t4(self):
        text = "We are carbon neutral and proud of our progress."
        ids = {f.tell_id for f in scan_tier1(text)}
        self.assertNotIn("T4", ids)


# --------------------------------------------------------------------------
# Prefilter
# --------------------------------------------------------------------------

class TestPrefilter(unittest.TestCase):
    def test_keeps_signal_blocks_drops_noise(self):
        text = (
            "The weather was pleasant at our annual gathering.\n\n"
            "We commit to net-zero by 2050 with a 50% reduction target.\n\n"
            "Lunch was catered."
        )
        out = prefilter(text)
        self.assertIn("net-zero", out)
        self.assertNotIn("Lunch was catered", out)

    def test_empty_when_no_signal(self):
        self.assertEqual(prefilter("Just some prose about nothing measurable."), "")

    def test_respects_char_budget(self):
        block = "We commit to a net-zero target. " * 100
        text = "\n\n".join([block] * 50)
        out = prefilter(text, char_budget=1000)
        self.assertLessEqual(len(out), 1000)


# --------------------------------------------------------------------------
# Pipeline — the four failure states + real labels + isolation
# --------------------------------------------------------------------------

class TestPipeline(unittest.TestCase):
    def test_extraction_raises_maps_to_extraction_failed(self):
        v = analyze_report(
            "Acme",
            "x.pdf",
            FakeExtractor(exc=ExtractionError("scanned image")),
            FakeLLM([]),
        )
        self.assertEqual(v.state, VerdictState.EXTRACTION_FAILED)
        self.assertFalse(v.is_publishable)

    def test_too_short_text_maps_to_extraction_failed(self):
        v = analyze_report("Acme", "x.pdf", FakeExtractor(text="tiny"), FakeLLM([]))
        self.assertEqual(v.state, VerdictState.EXTRACTION_FAILED)

    def test_malformed_json_twice_maps_to_analysis_failed(self):
        llm = FakeLLM(["not json", "still not json"])
        v = analyze_report("Acme", "x.pdf", FakeExtractor(text=LONG_BODY), llm)
        self.assertEqual(v.state, VerdictState.ANALYSIS_FAILED)
        self.assertEqual(llm.calls, 2)  # initial + one retry

    def test_retry_succeeds_after_one_bad_response(self):
        llm = FakeLLM(["broken", _payload()])  # 2nd call returns valid empty findings
        v = analyze_report("Acme", "x.pdf", FakeExtractor(text=LONG_BODY), llm)
        self.assertEqual(llm.calls, 2)
        self.assertEqual(v.state, VerdictState.RECOMMENDED)

    def test_all_quotes_dropped_maps_to_insufficient_data(self):
        # LLM proposes a fabricated quote; gate drops it; nothing else fires.
        llm = FakeLLM([_payload(
            {"tell_id": "T5", "quote": "this phrase is not in the report", "rationale": "r"}
        )])
        # Body with no Tier-1 triggers and a clean claim signal for prefilter.
        body = "We are committed to sustainability. " + ("Filler sentence. " * 60)
        v = analyze_report("Acme", "x.pdf", FakeExtractor(text=body), llm)
        self.assertEqual(v.state, VerdictState.INSUFFICIENT_DATA)

    def test_clean_report_recommended(self):
        llm = FakeLLM([_payload()])
        body = (
            "We report Scope 3 of 120,000 tCO2e and cut it 50% by 2030. "
            + ("We disclose our full inventory transparently. " * 30)
        )
        self.assertGreaterEqual(len("".join(body.split())), MIN_TEXT_CHARS)
        v = analyze_report("Acme", "x.pdf", FakeExtractor(text=body), llm)
        self.assertEqual(v.state, VerdictState.RECOMMENDED)

    def test_two_major_not_recommended_end_to_end(self):
        source = (
            "We are carbon neutral today through purchased offsets. "
            "We are industry-leading with an unbaselined reduction. "
            "Scope 1: 9,000 tCO2e. Scope 2: 4,000 tCO2e. " + ("narrative. " * 60)
        )
        llm = FakeLLM([_payload(
            {"tell_id": "T3", "quote": "carbon neutral today through purchased offsets",
             "rationale": "neutrality via offsets"},
            {"tell_id": "T1", "quote": "industry-leading with an unbaselined reduction",
             "rationale": "no baseline"},
        )])
        v = analyze_report("Acme", "x.pdf", FakeExtractor(text=source), llm)
        # Two MAJOR Tier-2 findings -> Not Recommended (Tier-1 T2 may also add).
        self.assertEqual(v.state, VerdictState.NOT_RECOMMENDED)
        self.assertGreaterEqual(v.major_count(), 2)

    def test_tier1_survives_analysis_failure(self):
        # Even if the LLM pass fails, Tier-1 omission findings are retained on the verdict.
        text = "Scope 1: 10,000 tCO2e. Scope 2: 5,000 tCO2e. " + ("net-zero by 2050. " * 40)
        llm = FakeLLM(["garbage", "garbage"])
        v = analyze_report("Acme", "x.pdf", FakeExtractor(text=text), llm)
        self.assertEqual(v.state, VerdictState.ANALYSIS_FAILED)
        self.assertTrue(any(f.tell_id == "T2" for f in v.findings))


# --------------------------------------------------------------------------
# source_hash — incremental batch dedup
# --------------------------------------------------------------------------

class TestSourceHash(unittest.TestCase):
    def test_stable(self):
        self.assertEqual(source_hash("abc"), source_hash("abc"))

    def test_content_sensitive(self):
        self.assertNotEqual(source_hash("abc"), source_hash("abd"))


if __name__ == "__main__":
    unittest.main()
