/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export: `next build` emits a fully static `out/` — no Node server at
  // runtime. Browsing hits the CDN, never the LLM or a live DB (the cost model).
  output: "export",

  // Verdict pages live at /companies/<slug>/. Trailing-slash keeps the exported
  // directory-index URLs stable on static hosts like Vercel.
  trailingSlash: true,

  // No next/image optimization server in a static export.
  images: { unoptimized: true },
};

module.exports = nextConfig;
