/**
 * Build-time readers for the JSON store produced by ../build_data.py.
 *
 * These run only at build time (in Server Components / generateStaticParams),
 * never in the browser — the site is a static export, so `fs` is fine here.
 *
 * The store is the frozen contract from the Python side:
 *   data/manifest.json         list of {slug, company, label, state, is_publishable}
 *   data/verdicts/<slug>.json  verdict.to_dict() + slug + provenance
 *   data/rubric.json           the TELLS catalog + label thresholds
 *
 * Everything degrades gracefully when the store is missing (fresh clone before
 * the batch has run): readers return empty structures instead of throwing, so
 * `next build` still produces a valid (empty) site.
 */

import fs from "node:fs";
import path from "node:path";

const DATA_DIR = path.join(process.cwd(), "data");
const VERDICTS_DIR = path.join(DATA_DIR, "verdicts");

// ---- Types (mirror the Python store shape) --------------------------------

export type Severity = "major" | "minor";
export type Tier = "tier1" | "tier2";

export interface Finding {
  tell_id: string;
  severity: Severity;
  tier: Tier;
  rationale: string;
  quote: string;
}

export interface Provenance {
  publisher?: string;
  edition_year?: number;
  title?: string;
  url?: string;
  retrieved?: string;
}

export interface Verdict {
  slug: string;
  company: string;
  state: string;
  label: string | null;
  source_hash: string;
  notes: string;
  findings: Finding[];
  provenance: Provenance;
}

export interface ManifestEntry {
  slug: string;
  company: string;
  label: string | null;
  state: string;
  is_publishable: boolean;
}

export interface RubricTell {
  tell_id: string;
  name: string;
  severity: Severity;
  tier: Tier;
  deferred: boolean;
  description: string;
}

export interface Threshold {
  label: string;
  rule: string;
}

export interface Rubric {
  tells: RubricTell[];
  thresholds: Threshold[];
}

// ---- Readers ---------------------------------------------------------------

function readJson<T>(file: string, fallback: T): T {
  try {
    return JSON.parse(fs.readFileSync(file, "utf-8")) as T;
  } catch {
    return fallback;
  }
}

/** Full manifest, in seed order (includes non-publishable entries). */
export function getManifest(): ManifestEntry[] {
  return readJson<ManifestEntry[]>(path.join(DATA_DIR, "manifest.json"), []);
}

/** Only the entries that get a public page (the three real labels). */
export function getPublishable(): ManifestEntry[] {
  return getManifest().filter((m) => m.is_publishable);
}

/** One verdict record by slug, or null if absent / not publishable. */
export function getVerdict(slug: string): Verdict | null {
  const record = readJson<Verdict | null>(
    path.join(VERDICTS_DIR, `${slug}.json`),
    null,
  );
  if (!record || record.label === null) return null; // never serve a failed state
  return record;
}

export function getRubric(): Rubric {
  return readJson<Rubric>(path.join(DATA_DIR, "rubric.json"), {
    tells: [],
    thresholds: [],
  });
}

/** Look up a tell's display name/description from the rubric by id. */
export function tellById(rubric: Rubric, tellId: string): RubricTell | undefined {
  return rubric.tells.find((t) => t.tell_id === tellId);
}
