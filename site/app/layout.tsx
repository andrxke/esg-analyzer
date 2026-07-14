import type { Metadata } from "next";
import Link from "next/link";
import { Fraunces, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

// Serif carries human judgment (verdicts, company names, prose).
const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-fraunces",
  display: "swap",
});

// Mono carries machine-verified fact (tell IDs, severities, hashes, the gate).
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "ESG Report Check — a greenwashing dossier, built from companies' own words",
    template: "%s — ESG Report Check",
  },
  description:
    "A Consumer-Reports-style verdict on corporate sustainability reports — backed by the company's own words, verified verbatim, against a published rubric.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${fraunces.variable} ${plexMono.variable}`}>
      <body>
        <header className="masthead">
          <div className="inner">
            <Link href="/" className="brand">
              ESG&nbsp;Report&nbsp;Check<span className="mk">.</span>
            </Link>
            <nav aria-label="Primary">
              <Link href="/">The Docket</Link>
              <Link href="/methodology/">Method</Link>
            </nav>
          </div>
        </header>
        <div className="container">{children}</div>
        <footer className="colophon">
          <div className="inner">
            Every label is our assessment of a company&apos;s own published report against a
            fixed, published rubric — an opinion grounded in stated criteria, not a factual
            accusation of intent. Findings quote the source verbatim.{" "}
            <Link href="/methodology/">Read the method &amp; disclaimer</Link>.
          </div>
        </footer>
      </body>
    </html>
  );
}
