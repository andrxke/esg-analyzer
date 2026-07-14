"""Tests for the build-time batch (site/build_data.py). Stdlib unittest, fakes, no network.

Covers the batch contract the site depends on:
  - slugify + rubric derivation from the TELLS catalog
  - build_one merges verdict.to_dict() with slug + provenance
  - manifest shape + publish filter (is_publishable tracks the label)
  - incremental skip: unchanged source_hash => the LLM is NOT called again
  - per-report isolation: a failed-state report is written but marked non-publishable
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

# build_data lives under site/ (not an installed package), so load it by path.
_BUILD_DATA_PATH = Path(__file__).resolve().parent.parent / "site" / "build_data.py"
_spec = importlib.util.spec_from_file_location("build_data", _BUILD_DATA_PATH)
build_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_data)


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

class KeyedExtractor:
    """Returns text by source path. Lets one batch have distinct per-company text."""

    def __init__(self, by_source: dict[str, str]):
        self._by_source = by_source

    def extract(self, source: str) -> str:
        # Match on suffix so callers can pass absolute resolved paths.
        for key, text in self._by_source.items():
            if source.endswith(key):
                return text
        from esg_analyzer.adapters import ExtractionError
        raise ExtractionError(f"no fake text for {source!r}")


class CountingLLM:
    """Always returns 'no findings'; records how many times complete() was called."""

    def __init__(self):
        self.calls = 0

    def complete(self, prompt: str, report_text: str) -> str:
        self.calls += 1
        return json.dumps({"findings": []})


# A report long enough to clear MIN_TEXT_CHARS and with no tells → RECOMMENDED.
_CLEAN = (
    "Our company published a full three-scope emissions inventory this year. "
    "Scope 1 was 10,000 tCO2e, Scope 2 was 5,000 tCO2e, and Scope 3 was 90,000 tCO2e. "
    "We reduced total emissions from 120,000 tCO2e in our 2019 baseline, with interim "
    "milestones in 2027 and 2030 on the path to our 2050 target. "
) * 6


class BuildDataTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        # Redirect the module's output dirs into a temp store.
        self._orig_data = build_data.DATA_DIR
        self._orig_verdicts = build_data.VERDICTS_DIR
        build_data.DATA_DIR = tmp / "data"
        build_data.VERDICTS_DIR = tmp / "data" / "verdicts"

    def tearDown(self):
        build_data.DATA_DIR = self._orig_data
        build_data.VERDICTS_DIR = self._orig_verdicts
        self._tmp.cleanup()

    # ---- pure helpers ----------------------------------------------------

    def test_slugify(self):
        self.assertEqual(build_data.slugify("H&M Group"), "h-m-group")
        self.assertEqual(build_data.slugify("Solid Co."), "solid-co")
        self.assertEqual(build_data.slugify("  Foo  Bar  "), "foo-bar")

    def test_build_rubric_shape(self):
        rubric = build_data.build_rubric()
        ids = {t["tell_id"] for t in rubric["tells"]}
        self.assertEqual(ids, {"T1", "T2", "T3", "T4", "T5", "T6"})
        # Every tell carries a UI description and severity/tier from the catalog.
        for t in rubric["tells"]:
            self.assertTrue(t["description"], f"{t['tell_id']} missing description")
            self.assertIn(t["severity"], {"major", "minor"})
        # T6 is present but flagged deferred.
        t6 = next(t for t in rubric["tells"] if t["tell_id"] == "T6")
        self.assertTrue(t6["deferred"])
        self.assertTrue(rubric["thresholds"])

    # ---- record assembly -------------------------------------------------

    def test_build_one_merges_slug_and_provenance(self):
        entry = {
            "slug": "clean-co",
            "company": "Clean Co.",
            "source": "clean.txt",
            "provenance": {"publisher": "Clean Co.", "edition_year": 2025},
        }
        ext = KeyedExtractor({"clean.txt": _CLEAN})
        llm = CountingLLM()
        record = build_data.build_one(entry, Path("/seed"), ext, llm)

        self.assertEqual(record["slug"], "clean-co")
        self.assertEqual(record["company"], "Clean Co.")
        self.assertEqual(record["provenance"]["publisher"], "Clean Co.")
        # verdict.to_dict() fields are present.
        self.assertIn("state", record)
        self.assertIn("findings", record)
        self.assertIn("source_hash", record)
        self.assertEqual(record["label"], "Recommended")

    # ---- incremental skip ------------------------------------------------

    def test_incremental_skip_avoids_second_llm_call(self):
        seed = [{
            "slug": "clean-co",
            "company": "Clean Co.",
            "source": "clean.txt",
            "provenance": {"publisher": "Clean Co."},
        }]
        seed_path = build_data.DATA_DIR.parent / "companies.json"
        seed_path.parent.mkdir(parents=True, exist_ok=True)
        seed_path.write_text(json.dumps(seed), encoding="utf-8")

        ext = KeyedExtractor({"clean.txt": _CLEAN})

        # First run: LLM called once.
        llm1 = CountingLLM()
        build_data.run_batch(seed_path, ext, llm1)
        self.assertEqual(llm1.calls, 1)

        # Second run, same source text (same hash): LLM must NOT be called.
        llm2 = CountingLLM()
        records = build_data.run_batch(seed_path, ext, llm2)
        self.assertEqual(llm2.calls, 0, "unchanged report should skip the LLM")
        self.assertEqual(records[0]["label"], "Recommended")

    def test_changed_source_reanalyzes(self):
        seed = [{"slug": "clean-co", "company": "Clean Co.", "source": "clean.txt",
                 "provenance": {}}]
        seed_path = build_data.DATA_DIR.parent / "companies.json"
        seed_path.parent.mkdir(parents=True, exist_ok=True)
        seed_path.write_text(json.dumps(seed), encoding="utf-8")

        llm1 = CountingLLM()
        build_data.run_batch(seed_path, KeyedExtractor({"clean.txt": _CLEAN}), llm1)
        self.assertEqual(llm1.calls, 1)

        # Different text → different hash → re-analyze.
        llm2 = CountingLLM()
        build_data.run_batch(seed_path, KeyedExtractor({"clean.txt": _CLEAN + " Extra."}), llm2)
        self.assertEqual(llm2.calls, 1, "changed report should re-run the LLM")

    # ---- manifest + publish filter --------------------------------------

    def test_manifest_and_publish_filter(self):
        seed = [
            {"slug": "clean-co", "company": "Clean Co.", "source": "clean.txt",
             "provenance": {}},
            {"slug": "thin-co", "company": "Thin Co.", "source": "thin.txt",
             "provenance": {}},
        ]
        seed_path = build_data.DATA_DIR.parent / "companies.json"
        seed_path.parent.mkdir(parents=True, exist_ok=True)
        seed_path.write_text(json.dumps(seed), encoding="utf-8")

        # thin.txt is below MIN_TEXT_CHARS → EXTRACTION_FAILED → non-publishable.
        ext = KeyedExtractor({"clean.txt": _CLEAN, "thin.txt": "too short"})
        build_data.run_batch(seed_path, ext, CountingLLM())

        manifest = json.loads((build_data.DATA_DIR / "manifest.json").read_text())
        by_slug = {m["slug"]: m for m in manifest}

        self.assertTrue(by_slug["clean-co"]["is_publishable"])
        self.assertEqual(by_slug["clean-co"]["label"], "Recommended")

        self.assertFalse(by_slug["thin-co"]["is_publishable"])
        self.assertIsNone(by_slug["thin-co"]["label"])
        self.assertEqual(by_slug["thin-co"]["state"], "extraction-failed")

        # Both verdict files are written (the operator keeps failures); rubric.json too.
        self.assertTrue((build_data.VERDICTS_DIR / "clean-co.json").exists())
        self.assertTrue((build_data.VERDICTS_DIR / "thin-co.json").exists())
        self.assertTrue((build_data.DATA_DIR / "rubric.json").exists())


if __name__ == "__main__":
    unittest.main()
