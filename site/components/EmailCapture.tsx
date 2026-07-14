"use client";

/**
 * Email capture (T6). Posts to a free third-party list service — no backend of
 * our own, so the site stays a pure static export ($0 to serve).
 *
 * Set NEXT_PUBLIC_NEWSLETTER_ACTION to your provider's form endpoint, e.g.
 *   Buttondown: https://buttondown.com/api/emails/embed-subscribe/<username>
 *   Formspree:  https://formspree.io/f/<form-id>
 * If unset, the form falls back to a mailto: so nothing is silently dropped.
 *
 * The form works without JS (native submit to the action). The client JS only
 * adds an inline "looks invalid" hint before submit.
 */

import { useState } from "react";

const ACTION = process.env.NEXT_PUBLIC_NEWSLETTER_ACTION || "";
const EMAIL_FIELD = process.env.NEXT_PUBLIC_NEWSLETTER_FIELD || "email";

export default function EmailCapture() {
  const [error, setError] = useState<string | null>(null);

  const action = ACTION || "mailto:hello@example.com";
  const method = ACTION ? "post" : "get";

  return (
    <section className="subscribe" aria-labelledby="ec-heading">
      <p className="eyebrow">The dispatch</p>
      <h2 id="ec-heading">New verdict, in your inbox</h2>
      <p>One short email when a company is added to the docket. No spam, no filler.</p>
      <form
        action={action}
        method={method}
        target="_blank"
        onSubmit={(e) => {
          const input = e.currentTarget.elements.namedItem(
            EMAIL_FIELD,
          ) as HTMLInputElement | null;
          const value = input?.value.trim() ?? "";
          if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) {
            e.preventDefault();
            setError("Enter a valid email address.");
            return;
          }
          setError(null);
        }}
      >
        <label htmlFor="ec-email" className="sr-only">
          Email address
        </label>
        <input
          id="ec-email"
          type="email"
          name={EMAIL_FIELD}
          placeholder="you@example.com"
          required
          aria-describedby={error ? "ec-error" : undefined}
        />
        <button type="submit" className="btn">
          Subscribe
        </button>
      </form>
      {error && (
        <p id="ec-error" role="alert" className="err">
          {error}
        </p>
      )}
      {!ACTION && (
        <p className="hint">Set NEXT_PUBLIC_NEWSLETTER_ACTION to wire this to a real list.</p>
      )}
    </section>
  );
}
