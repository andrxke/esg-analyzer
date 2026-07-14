/**
 * Company-request intake (T6). A link to a free third-party form (Tally / Google
 * Form / Formspree) — the one request-time write, deliberately offloaded so the
 * site itself stays fully static and $0 (DESIGN.md "company-request intake").
 *
 * Set NEXT_PUBLIC_REQUEST_FORM_URL to your form's public URL. If unset, the link
 * is rendered as a note, so the section never points at a dead URL.
 *
 * Server Component (no interactivity) — just a link.
 */

const FORM_URL = process.env.NEXT_PUBLIC_REQUEST_FORM_URL || "";

export default function RequestForm() {
  return (
    <section className="request" aria-labelledby="rf-heading">
      <p className="eyebrow">Petition the docket</p>
      <h2 id="rf-heading">A report that deserves a look?</h2>
      <p>Name a company and we&apos;ll weigh it for the next batch of filings.</p>
      {FORM_URL ? (
        <a
          className="btn"
          href={FORM_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          Request a company →
        </a>
      ) : (
        <p className="hint">
          Set NEXT_PUBLIC_REQUEST_FORM_URL to a Tally / Google Form URL to enable this.
        </p>
      )}
    </section>
  );
}
