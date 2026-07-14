import Link from "next/link";
import type { Metadata } from "next";
import { getRubric } from "@/lib/verdicts";

export const metadata: Metadata = {
  title: "Method & disclaimer",
  description:
    "How the ESG Report Check verdict is reached: a fixed, published rubric applied to a company's own report. An opinion grounded in stated criteria, not an accusation.",
};

export default function MethodologyPage() {
  const rubric = getRubric();
  const active = rubric.tells.filter((t) => !t.deferred);
  const deferred = rubric.tells.filter((t) => t.deferred);

  return (
    <div className="prose">
      <p className="eyebrow">Method &amp; disclaimer</p>
      <h1 style={{ fontSize: "clamp(2.2rem, 6vw, 3.2rem)", margin: "0.4rem 0 0" }}>
        How a verdict is reached
      </h1>

      <p style={{ fontSize: "1.15rem", marginTop: "1.5rem" }}>
        Each label is <strong>our assessment of a company&apos;s own published sustainability
        report</strong>, measured against the fixed rubric below. It is an{" "}
        <strong>opinion grounded in stated criteria</strong> — the spirit of a Consumer Reports
        or Wired verdict — <strong>not a factual accusation</strong> that a company is lying or
        greenwashing. The tells describe characteristics of a <em>report</em>, not the motives
        of the people who wrote it.
      </p>

      <p>
        Every finding on a verdict page either quotes the report{" "}
        <strong>verbatim</strong> — checked character-for-character against the source text
        before it is published — or names a specific, defined omission. We never paraphrase a
        claim into something the company did not write.
      </p>

      <h2>What the labels mean</h2>
      <ul>
        <li>
          <strong>Recommended</strong> means “no major greenwashing tells found in this
          report.” It is <strong>not an endorsement</strong> of the company, its products, or
          its overall environmental record.
        </li>
        <li>
          <strong>Improving</strong> means some tells are present, but not enough to reach Not
          Recommended.
        </li>
        <li>
          <strong>Not Recommended</strong> means multiple major tells are present in the
          report.
        </li>
        <li>
          <strong>insufficient-data</strong> reports are never published — a report we could
          not read or that was too thin to judge is <em>not</em> quietly labeled Recommended.
        </li>
      </ul>

      <h2>The tells</h2>
      <p className="muted">
        Each tell is defined so two people applying it to the same report reach the same
        finding. Major tells drive the label; minor tells alone can never reach Not
        Recommended.
      </p>
      <table className="dossier-table">
        <thead>
          <tr>
            <th>Tell</th>
            <th>Severity</th>
            <th>What it means</th>
          </tr>
        </thead>
        <tbody>
          {active.map((t) => (
            <tr key={t.tell_id}>
              <td>{t.name}</td>
              <td className="cap">{t.severity}</td>
              <td>{t.description}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {deferred.length > 0 && (
        <p className="muted" style={{ fontSize: "0.9rem" }}>
          Defined but not yet applied: {deferred.map((t) => t.name).join(", ")} — coming in a
          later release.
        </p>
      )}

      <h2>How the label is decided</h2>
      <p className="muted">
        The label is a function of tell <em>severity</em>, not the raw count.
      </p>
      <table className="dossier-table">
        <thead>
          <tr>
            <th>Label</th>
            <th>Rule</th>
          </tr>
        </thead>
        <tbody>
          {rubric.thresholds.map((th) => (
            <tr key={th.label}>
              <td>{th.label}</td>
              <td>{th.rule}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Disclaimer</h2>
      <p className="muted">
        This site analyzes publicly available reports for editorial and educational purposes.
        Labels reflect our reading of those documents against the criteria above and may not
        reflect a company&apos;s full environmental performance, subsequent disclosures, or
        context outside the analyzed report. Company names and report titles belong to their
        respective owners. The source is cited on every verdict page — if you believe a verdict
        misreads a report, we welcome corrections.
      </p>

      <p style={{ marginTop: "2.5rem" }}>
        <Link href="/">← Back to the docket</Link>
      </p>
    </div>
  );
}
