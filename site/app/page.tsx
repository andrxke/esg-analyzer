import Link from "next/link";
import { getPublishable } from "@/lib/verdicts";
import { chipClass } from "@/lib/labels";
import EmailCapture from "@/components/EmailCapture";
import RequestForm from "@/components/RequestForm";

export default function HomePage() {
  const companies = getPublishable();

  return (
    <>
      <section className="hero">
        <p className="eyebrow">The greenwashing docket</p>
        <h1>We read the report so the claims can&apos;t hide.</h1>
        <p className="lede">
          Companies publish glossy sustainability reports. We assess each one against a{" "}
          <strong>fixed, published rubric</strong> and file a verdict —{" "}
          <strong>Recommended</strong>, <strong>Improving</strong>, or{" "}
          <strong>Not Recommended</strong> — backed by the report&apos;s own words, quoted
          verbatim. <Link href="/methodology/">How the verdict is reached.</Link>
        </p>
      </section>

      {companies.length === 0 ? (
        <p className="muted" style={{ marginTop: "2.5rem" }}>
          No cases filed yet. Run <span className="mono">npm run data</span> to populate the
          docket.
        </p>
      ) : (
        <div className="ledger" role="table" aria-label="Filed verdicts">
          <div className="ledger-head" role="row">
            <span role="columnheader">No.</span>
            <span role="columnheader">Company</span>
            <span role="columnheader" className="r">
              Verdict
            </span>
          </div>
          {companies.map((c, i) => (
            <Link
              key={c.slug}
              href={`/companies/${c.slug}/`}
              className="case"
              role="row"
            >
              <span className="no" role="cell">
                {String(i + 1).padStart(3, "0")}
              </span>
              <span className="co" role="cell">
                {c.company}
                <span className="sub">Sustainability report · analyzed</span>
              </span>
              <span role="cell" style={{ textAlign: "right" }}>
                <span className={chipClass(c.label)}>{c.label}</span>
              </span>
            </Link>
          ))}
        </div>
      )}

      <EmailCapture />
      <RequestForm />
    </>
  );
}
