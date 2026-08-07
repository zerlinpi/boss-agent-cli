from __future__ import annotations

import sys
import types

import pytest

from boss_agent_cli.web import documents
from boss_agent_cli.web.documents import DocumentParseError, parse_uploaded_document


def test_oversized_base64_is_rejected_before_decode(monkeypatch):
	called = False
	original = documents.base64.b64decode

	def guarded_decode(*args, **kwargs):
		nonlocal called
		called = True
		return original(*args, **kwargs)

	monkeypatch.setattr(documents.base64, "b64decode", guarded_decode)
	with pytest.raises(DocumentParseError, match="12 MB"):
		parse_uploaded_document({
			"name": "large.pdf",
			"content_base64": "A" * (documents.MAX_BASE64_CHARS + 1),
		})
	assert called is False


def test_pdf_page_limit_is_checked_before_page_text_extraction(monkeypatch):
	class Page:
		def extract_text(self):
			raise AssertionError("page extraction should not run beyond the page-count guard")

	class Reader:
		def __init__(self, stream):
			self.pages = [Page() for _ in range(documents.MAX_PDF_PAGES + 1)]

	module = types.ModuleType("pypdf")
	module.PdfReader = Reader
	monkeypatch.setitem(sys.modules, "pypdf", module)

	with pytest.raises(DocumentParseError, match="页数超过"):
		documents._parse_pdf(b"%PDF-1.7 fake")
