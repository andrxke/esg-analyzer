"""Edge adapters — the only place that touches third-party libs or the network.

The core pipeline depends on these two Protocols, never on a concrete PDF
library or LLM SDK. That keeps the whole test suite runnable with zero installs
(tests inject fakes) and confines the one real cost — LLM calls — to a single
swappable seam used by the batch runner and the golden-set eval.

    core pipeline ──depends-on──▶ TextExtractor (Protocol)
                   ──depends-on──▶ LLMClient    (Protocol)
                                        ▲
              real impls injected at the edge (batch runner / eval)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class ExtractionError(RuntimeError):
    """Raised by a TextExtractor when a source cannot be read at all."""


@runtime_checkable
class TextExtractor(Protocol):
    """Turns a source (PDF path or URL) into plain text.

    Implementations may raise ExtractionError for unreadable input; the pipeline
    also applies its own length/quality guard on whatever text is returned, so an
    extractor that returns near-empty garbage is handled without raising.
    """

    def extract(self, source: str) -> str: ...


@runtime_checkable
class LLMClient(Protocol):
    """Runs the Tier-2 pass: given filtered report text, return a JSON string.

    The returned string is parsed and strictly validated by schema.py. The client
    is responsible only for transport; it must NOT be trusted to return valid
    shape — validation + one retry + ANALYSIS_FAILED live in the pipeline.
    """

    def complete(self, prompt: str, report_text: str) -> str: ...


class PdfTextExtractor:
    """Real PDF/text extractor. Imports its PDF backend lazily so importing this
    module (and thus the core package) never requires the dependency to be present.

    v1 marks scanned-image PDFs as extraction-failed upstream (no OCR — deferred).
    """

    def extract(self, source: str) -> str:
        if source.lower().endswith((".txt", ".md")):
            with open(source, "r", encoding="utf-8", errors="replace") as fh:
                return fh.read()

        if source.lower().endswith(".pdf"):
            try:
                from pypdf import PdfReader  # lazy: only needed for real PDFs
            except ImportError as exc:  # pragma: no cover - env-dependent
                raise ExtractionError(
                    "PDF extraction needs 'pypdf' (pip install pypdf)"
                ) from exc
            try:
                reader = PdfReader(source)
                return "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception as exc:  # pragma: no cover - backend-dependent
                raise ExtractionError(f"failed to read PDF {source!r}: {exc}") from exc

        # URL fetching is a deliberate v1 gap for the batch path (curated files on
        # disk). Left explicit rather than silently mis-handling arbitrary sources.
        raise ExtractionError(f"unsupported source type: {source!r}")
