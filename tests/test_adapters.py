"""Tests for the edge adapters: PdfTextExtractor error handling + contract.

The pipeline tests inject fakes, which means the real PdfTextExtractor has never
been tested directly. These tests exercise the three paths: .txt extraction,
unsupported extensions, and missing files. PDF extraction requires pypdf and a
fixture, tested separately when the dependency is present.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from esg_analyzer.adapters import PdfTextExtractor, ExtractionError


REPO_ROOT = Path(__file__).resolve().parent.parent


class TestPdfTextExtractorTxt(unittest.TestCase):
    """Exercise the .txt / .md extraction path on real files."""

    def test_extracts_txt_file(self):
        """Should return the full file contents for a .txt file."""
        fixture = REPO_ROOT / "eval" / "samples" / "solid_co.txt"
        ext = PdfTextExtractor()
        text = ext.extract(str(fixture))
        self.assertIn("Solid Co.", text)
        self.assertIn("Scope 3", text)

    def test_extracts_md_file(self):
        """Should return the full file contents for a .md file."""
        fixture = REPO_ROOT / "docs" / "rubric.md"
        ext = PdfTextExtractor()
        text = ext.extract(str(fixture))
        self.assertIn("The Tells Rubric", text)

    def test_unsupported_extension_raises(self):
        """An unsupported file type (e.g. .xlsx) must raise ExtractionError."""
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(b"fake excel content")
            path = f.name
        try:
            ext = PdfTextExtractor()
            with self.assertRaises(ExtractionError) as ctx:
                ext.extract(path)
            self.assertIn("unsupported source type", str(ctx.exception))
        finally:
            os.unlink(path)

    def test_missing_txt_file_raises(self):
        """A nonexistent .txt file must raise (FileNotFoundError)."""
        ext = PdfTextExtractor()
        with self.assertRaises(FileNotFoundError):
            ext.extract("/nonexistent/path/to/report.txt")

    def test_missing_pdf_file_raises_extraction_error(self):
        """A nonexistent .pdf file must raise ExtractionError."""
        ext = PdfTextExtractor()
        with self.assertRaises(ExtractionError):
            ext.extract("/nonexistent/path/to/report.pdf")

    def test_empty_txt_file(self):
        """An empty .txt file returns empty string (pipeline's length guard
        catches this and maps to EXTRACTION_FAILED)."""
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            path = f.name
        try:
            ext = PdfTextExtractor()
            text = ext.extract(path)
            self.assertEqual(text, "")
        finally:
            os.unlink(path)


class TestExtractionError(unittest.TestCase):
    """ExtractionError is a RuntimeError that carries a message."""

    def test_is_runtime_error(self):
        self.assertIsInstance(ExtractionError("test"), RuntimeError)

    def test_message_preserved(self):
        e = ExtractionError("scanned image PDF")
        self.assertEqual(str(e), "scanned image PDF")


if __name__ == "__main__":
    unittest.main()
