import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import {
  getPublishable,
  getVerdict,
  getRubric,
  tellById,
} from "@/lib/verdicts";
import { stampClass, stampTag, labelGloss } from "@/lib/labels";
import EmailCapture from "@/components/EmailCapture";

// Static export: pre-render one page per publishable company.
export function generateStaticParams() {
  return getPublishable().map((c) => ({ slug: c.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const verdict = getVerdict(slug);
  if (!verdict) return {};
  return {
    title: `${verdict.company}: ${verdict.label}`,
    description: `Our assessment of ${verdict.company}'s published sustainability report against a fixed greenwashing rubric: ${verdict.label}.`,
  };
}

export default async function VerdictPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const verdict = getVerdict(slug);
  if (!verdict) notFound();

  const rubric = getRubric();
  const p = verdict.provenance || {};
  const firedTellIds = Array.from(new Set(verdict.findings.map((f) => f.tell_id)));

  return (
    <>
      <p className="backlink">
        <Link href="/">← The docket</Link>
      </p>

      <div className="case-head">
        <div>
          <p className="eyebrow">Case file · {slug}</p>
          <h1>{verdict.company}</h1>
          <p className="gloss">{labelGloss(verdict.label)}</p>
        </div>
        <div className="stamp-wrap">
          <span className={stampClass(verdict.label)} role="img"
                aria-label={`Verdict: ${verdict.label}`}>
            <span className="tag">{stampTag(verdict.label)}</span>
            <span className="verdict">{verdict.label}</span>
          </span>
        </div>
      </div>

      {/* T5: label-as-opinion framing — the real legal surface. */}
      <p className="standfirst">
        This is <strong>our assessment</strong> of {verdict.company}&apos;s{" "}
        <strong>own published report</strong>, measured against the criteria below. It is an
        opinion grounded in a fixed, published rubric — not a factual claim about the
        company&apos;s intent. Every finding quotes the report verbatim or names a specific
        omission. <Link href="/methodology/">Read the full method.</Link>
      </p>

      {/* T4: findings as numbered exhibits — the company's own words. */}
      <h2 className="section-label">Exhibits · what we found</h2>
      {verdict.findings.length === 0 ? (
        <p className="exhibit--nofindings" style={{ padding: "1.5rem 0" }}>
          No greenwashing tells fired against the current rubric.
        </p>
      ) : (
        verdict.findings.map((f, i) => {
          const tell = tellById(rubric, f.tell_id);
          return (
            <div key={i} className="exhibit">
              <div className="idx">EX-{String(i + 1).padStart(2, "0")}</div>
              <div>
                <div className="tell">
                  <span className="name">{tell ? tell.name : f.tell_id}</span>
                  <span className={`sev sev--${f.severity}`}>
                    {f.severity} · {f.tier}
                  </span>
                </div>
                <p className="rationale">{f.rationale}</p>
                {f.quote && (
                  <blockquote>
                    “{f.quote}”
                    <span className="verify">✓ verified verbatim against source</span>
                    <cite>
                      {verdict.company}
                      {p.title ? ` · ${p.title}` : ""}
                    </cite>
                  </blockquote>
                )}
              </div>
            </div>
          );
        })
      )}

      {/* T5: the criteria the label derived from, shown on-page. */}
      {firedTellIds.length > 0 && (
        <>
          <h2 className="section-label">The criteria applied</h2>
          <table className="dossier-table">
            <thead>
              <tr>
                <th>Tell</th>
                <th>Severity</th>
                <th>What it means</th>
              </tr>
            </thead>
            <tbody>
              {firedTellIds.map((id) => {
                const t = tellById(rubric, id);
                if (!t) return null;
                return (
                  <tr key={id}>
                    <td>{t.name}</td>
                    <td className="cap">{t.severity}</td>
                    <td>{t.description}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="muted" style={{ fontSize: "0.9rem", marginTop: "0.75rem" }}>
            See the <Link href="/methodology/">full rubric and label thresholds</Link>.
          </p>
        </>
      )}

      {/* Report freshness / sourcing — protects legally and builds trust. */}
      <div className="provenance">
        <h2 className="section-label">Source of record</h2>
        <dl>
          <dt>Report</dt>
          <dd>
            {p.title || "Published sustainability report"}
            {p.edition_year ? ` (${p.edition_year})` : ""}
          </dd>
          {p.publisher && (
            <>
              <dt>Publisher</dt>
              <dd>{p.publisher}</dd>
            </>
          )}
          {p.url && (
            <>
              <dt>Original</dt>
              <dd>
                <a href={p.url} target="_blank" rel="noopener noreferrer">
                  {p.url}
                </a>
              </dd>
            </>
          )}
          {p.retrieved && (
            <>
              <dt>Retrieved</dt>
              <dd className="mono">{p.retrieved}</dd>
            </>
          )}
          {verdict.source_hash && (
            <>
              <dt>Source&nbsp;hash</dt>
              <dd className="mono">{verdict.source_hash.slice(0, 16)}…</dd>
            </>
          )}
        </dl>
      </div>

      <EmailCapture />
    </>
  );
}
