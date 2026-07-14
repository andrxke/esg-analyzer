#!/usr/bin/env python3
"""Build-time batch: analyze the curated company set → JSON store the site reads.

    python3 site/build_data.py                    # uses site/companies.json
    python3 site/build_data.py path/to/seed.json  # alternate seed manifest

This is the Python→JS bridge. It runs the analyzer over each curated report and
writes a static JSON store the Next.js build consumes at build time (no runtime
DB, no live LLM — browsing hits the CDN). The one real cost, the Tier-2 LLM call,
is confined here and made incremental so it stays flat as coverage grows.

    site/companies.json            seed manifest (hand-authored: slug + provenance)
            │
            ▼  analyze_report() per company, incremental via source_hash
    site/data/
        manifest.json              [{slug, company, label, state, is_publishable}]
        verdicts/<slug>.json       verdict.to_dict() + slug + provenance
        rubric.json                the TELLS catalog + label thresholds (for the UI)

Incremental (DESIGN.md "incremental batch"): each report's source text is content-
hashed; if the stored verdict's hash matches, the LLM is NOT called and the existing
verdict is kept. Adding one company costs exactly one analysis; re-running is free.

Per-report isolation: analyze_report never raises for report-specific problems, so
one bad report writes its failure-state verdict and the batch continues.

Needs the same env as the eval:  pip install pypdf openai;  export OPENROUTER_API_KEY=...
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Allow running as `python3 site/build_data.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from esg_analyzer.adapters import PdfTextExtractor, ExtractionError, TextExtractor, LLMClient  # noqa: E402
from esg_analyzer.openrouter_client import OpenRouterClient  # noqa: E402
from esg_analyzer.pipeline import analyze_report, source_hash  # noqa: E402
from esg_analyzer.rubric import TELLS  # noqa: E402
from esg_analyzer.models import Verdict  # noqa: E402

SITE_DIR = Path(__file__).resolve().parent
DEFAULT_SEED = SITE_DIR / "companies.json"
DATA_DIR = SITE_DIR / "data"
VERDICTS_DIR = DATA_DIR / "verdicts"

# One-line "what it is" per tell for the UI / methodology page. The prose source
# of truth is docs/rubric.md; these are the short labels the site renders.
TELL_DESCRIPTIONS: dict[str, str] = {
    "T1": "A reduction or improvement claim with no baseline value and no baseline year — "
          "progress you can't measure against a starting point.",
    "T2": "Scope 1/2 emissions are disclosed but Scope 3 (usually the majority of the real "
          "footprint) is absent or given no number.",
    "T3": "A 'carbon neutral' / 'net zero today' claim achieved mostly through purchased "
          "offsets rather than actual emissions cuts.",
    "T4": "A far-off target (e.g. net-zero 2050) with no nearer interim milestone and no "
          "stated path to get there.",
    "T5": "Qualitative bragging — 'industry-leading', 'world-class' — standing in for any "
          "measurable performance figure.",
    "T6": "A target present in last year's report is absent or weakened this year "
          "(deferred to a later release).",
}

# The label thresholds, mirrored from docs/rubric.md so the methodology page renders
# from a single structured source instead of hardcoded prose in the frontend.
LABEL_THRESHOLDS = [
    {"label": "Not Recommended", "rule": "2 or more Major tells."},
    {"label": "Improving", "rule": "Exactly 1 Major tell, or 2+ Minor tells with no Major."},
    {"label": "Recommended", "rule": "0 Major tells and at most 1 Minor tell."},
    {"label": "insufficient-data",
     "rule": "Extraction failed, report too thin to assess, or all quotes dropped by the "
             "verbatim-quote gate. Never collapses to Recommended."},
]


def slugify(name: str) -> str:
    """URL-safe slug from a company name. Manifest slugs override this."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def load_seed(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_existing_verdict(slug: str) -> dict | None:
    p = VERDICTS_DIR / f"{slug}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None  # corrupt store entry → treat as absent, re-analyze


def build_rubric() -> dict:
    """Derive the rubric the UI renders from the code catalog (single source of truth)."""
    tells = []
    for tell in TELLS.values():
        tells.append({
            "tell_id": tell.tell_id,
            "name": tell.name,
            "severity": tell.severity.value,
            "tier": tell.tier.value,
            "deferred": tell.deferred,
            "description": TELL_DESCRIPTIONS.get(tell.tell_id, ""),
        })
    return {"tells": tells, "thresholds": LABEL_THRESHOLDS}


def build_one(
    entry: dict,
    seed_dir: Path,
    extractor: TextExtractor,
    llm: LLMClient,
) -> dict:
    """Analyze one company (incremental) and return the store record to write.

    The record is verdict.to_dict() plus `slug` and `provenance` from the seed —
    the Verdict model stays free of presentation concerns.
    """
    company = entry["company"]
    slug = entry.get("slug") or slugify(company)
    provenance = entry.get("provenance", {})
    source = str((seed_dir / entry["source"]).resolve())

    # Incremental skip: hash the source text; if it matches the stored verdict,
    # keep it and never touch the LLM.
    try:
        text = extractor.extract(source)
        shash = source_hash(text)
    except ExtractionError:
        shash = None  # can't hash unreadable input; fall through to the pipeline

    if shash is not None:
        existing = load_existing_verdict(slug)
        if existing and existing.get("source_hash") == shash:
            print(f"  = {slug}: unchanged (hash match) — skipping LLM")
            # Refresh slug/provenance in case the seed changed, keep the verdict body.
            existing["slug"] = slug
            existing["provenance"] = provenance
            return existing

    verdict = analyze_report(company, source, extractor, llm)
    record = verdict.to_dict()
    record["slug"] = slug
    record["provenance"] = provenance
    flag = "✓ publish" if verdict.is_publishable else "· excluded"
    print(f"  {flag} {slug}: {verdict.state.value}")
    return record


def write_store(records: list[dict]) -> None:
    VERDICTS_DIR.mkdir(parents=True, exist_ok=True)

    for record in records:
        (VERDICTS_DIR / f"{record['slug']}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    manifest = [
        {
            "slug": r["slug"],
            "company": r["company"],
            "label": r["label"],
            "state": r["state"],
            "is_publishable": r["label"] is not None,
        }
        for r in records
    ]
    (DATA_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    (DATA_DIR / "rubric.json").write_text(
        json.dumps(build_rubric(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_batch(
    seed_path: Path,
    extractor: TextExtractor,
    llm: LLMClient,
) -> list[dict]:
    """Analyze every company in the seed and write the JSON store. Returns records."""
    seed = load_seed(seed_path)
    seed_dir = seed_path.resolve().parent

    records: list[dict] = []
    for entry in seed:
        records.append(build_one(entry, seed_dir, extractor, llm))

    write_store(records)
    return records


def main(argv: list[str]) -> int:
    seed_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_SEED
    if not seed_path.exists():
        print(f"ERROR: seed manifest not found: {seed_path}")
        return 1

    print(f"Building store from {seed_path} ...\n")
    records = run_batch(seed_path, PdfTextExtractor(), OpenRouterClient())

    published = sum(1 for r in records if r["label"] is not None)
    excluded = len(records) - published
    print(f"\nDone. {len(records)} analyzed → {published} published, "
          f"{excluded} excluded (failed/insufficient).")
    print(f"Store written to {DATA_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
