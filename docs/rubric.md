# The Tells Rubric — ESG Greenwashing Analyzer

Status: DRAFT (T1 — the product spine). Everything downstream (label logic, the
methodology/disclaimer page, the golden-set eval) is built against this document.

This rubric is the basis for the **label-as-opinion framing**: a verdict is our assessment of a
report against these published, objective criteria — not a factual accusation of intent. Every
tell below is defined so two people applying it to the same report would reach the same finding.

---

## The Tells

Each tell lists: what it is, why it signals greenwashing, how it's detected (Tier 1 = cheap
presence/absence scan over the whole report; Tier 2 = filtered LLM pass for quoted evidence),
the evidence to capture, and its **severity** (Major / Minor).

### T1 — Unbaselined headline claim  ·  MAJOR
- **What:** A reduction or improvement claim with no baseline value AND no baseline year.
  "We cut emissions" / "significant progress on our footprint" with no "from X tonnes in YYYY."
- **Why it's a tell:** A reduction claim you can't measure against a starting point is unfalsifiable.
  It's the most common way to sound like progress without committing to any.
- **Detection:** Tier 2 — LLM finds the reduction/improvement claim, checks for an adjacent
  baseline (value + year). Verbatim quote of the claim required.
- **Evidence:** the quoted claim + confirmation that no baseline appears with it.

### T2 — Missing or unquantified Scope 3  ·  MAJOR
- **What:** The report discloses Scope 1 and/or Scope 2 emissions but Scope 3 is absent, or named
  but given no number.
- **Why it's a tell:** Scope 3 (value chain) is typically the large majority of a company's real
  footprint. Reporting only Scope 1/2 makes the number look small and controllable.
- **Detection:** Tier 1 — presence scan over the whole report: does "Scope 3" appear? Is it
  accompanied by a figure (tCO2e)? This is the classic omission tell and MUST be checked against
  the full document, not an excerpt.
- **Evidence:** presence/absence of the term and of an associated number.

### T3 — Offset-dependent neutrality  ·  MAJOR
- **What:** A "carbon neutral" / "net zero (today)" claim achieved mostly through purchased
  offsets rather than actual emissions reductions.
- **Why it's a tell:** Neutrality bought with offsets is not the same as cutting emissions;
  presenting it as equivalent is the substance of many greenwashing complaints.
- **Detection:** Tier 2 — LLM finds the neutrality claim AND how it's achieved (offsets vs.
  reductions). Only flag when offsets are the stated primary mechanism.
- **Evidence:** the quoted neutrality claim + the quoted mechanism.

### T4 — Long-dated target, no interim milestones  ·  MINOR
- **What:** A far-off target (e.g. net-zero 2050) with no nearer checkpoints (2030 / 2035) and no
  stated path.
- **Why it's a tell:** A target beyond the tenure of everyone currently accountable, with no
  interim steps, is a promise no one can be held to.
- **Detection:** Tier 1 presence (is there a target year? are interim years present near it?) +
  Tier 2 to confirm no path is described.
- **Evidence:** the quoted target + confirmation no interim milestone appears.

### T5 — Vague superlative, no number  ·  MINOR
- **What:** "Industry-leading," "world-class," "deeply committed to sustainability," "among the
  greenest" — qualitative bragging with no quantification.
- **Why it's a tell:** Marketing language standing in for measurable performance.
- **Detection:** Tier 2. **Use with restraint** — these phrases are everywhere and, alone, are
  weak. Only capture ones presented as substantive claims, not boilerplate mission language.
- **Evidence:** the quoted superlative.

### T6 — Goalpost shifting  ·  MAJOR  ·  DEFERRED (fast-follow #2)
- **What:** A target present in last year's report is absent or weakened this year.
- **Why it's a tell:** The single most damning, hardest-to-spin signal — and the shareable one.
- **Status:** Not in v1 (needs two sourced editions + structured target diff). Defined here so the
  rubric is complete and the label logic reserves a slot for it.

---

## Label Logic

Labels are a function of **severity**, not the raw count of tells.

- **Major tells:** T1 (unbaselined headline claim), T2 (missing Scope 3), T3 (offset-dependent
  neutrality). [T6 goalpost — Major, once v1+1.]
- **Minor tells:** T4 (no interim milestones), T5 (vague superlative).

### Boundaries (DECIDED 2026-07-10: moderate strictness — 2+ Major tells = Not Recommended)

Chosen deliberately over strict (3 Major, too toothless) and aggressive (1 Major, most viral but
most fragile). Moderate gives the site real teeth on a defensible floor for day one, when
tolerance for a dispute is lowest. The dial is a one-line change if you want to tighten or loosen
it later once the pipeline is trusted.

| Label | Rule |
|-------|------|
| **Not Recommended** | **2 or more Major tells.** |
| **Improving** | **Exactly 1 Major tell**, OR **2+ Minor tells** with no Major. |
| **Recommended** | **0 Major tells and ≤1 Minor tell.** |
| **insufficient-data** | Extraction failed, report too thin/truncated to assess, or all findings dropped by the verbatim-quote gate. **Never** collapses to Recommended. |

Guardrails baked in:
- Minor tells alone can never produce **Not Recommended** — they cap at Improving. This keeps a
  company with only buzzwords from being labeled as harshly as one hiding its Scope 3.
- "Recommended" is not "good," it's "no major greenwashing tells found in this report." The
  methodology page must state this explicitly (label-as-opinion framing).

---

## Notes for the methodology/disclaimer page (D8)

- State that the label is **our assessment against the criteria above**, applied to the company's
  **own published report** — an opinion grounded in stated criteria, not a claim about intent.
- Never use "lying" or assert "greenwashing" as a factual conclusion about the company; the tells
  describe report characteristics, not motive.
- Every verdict page shows the tells triggered + the verbatim evidence + the report edition cited.
