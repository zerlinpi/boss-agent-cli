"""Resume document parsing for the local recruiter Web console."""

from __future__ import annotations

import base64
import json
import re
import zlib
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

MAX_DOCUMENT_BYTES = 12 * 1024 * 1024
MAX_DOCX_EXPANDED_BYTES = 32 * 1024 * 1024
MAX_EXTRACTED_CHARS = 120_000
MAX_JSON_CHARS = 500_000
SUPPORTED_EXTENSIONS = (".json", ".txt", ".md", ".pdf", ".docx")


class DocumentParseError(ValueError):
	"""Raised when an uploaded resume cannot be safely parsed."""


def _decode_bytes(raw: bytes) -> str:
	for encoding in ("utf-8-sig", "utf-8", "gb18030"):
		try:
			return raw.decode(encoding)
		except UnicodeDecodeError:
			continue
	raise DocumentParseError("文本编码无法识别，请转换为 UTF-8 后重试")


def _read_payload(entry: dict[str, Any]) -> tuple[str, bytes]:
	name = Path(str(entry.get("name") or "resume")).name
	encoded = entry.get("content_base64")
	if not isinstance(encoded, str) or not encoded:
		raise DocumentParseError(f"{name}: 缺少文件内容")
	try:
		raw = base64.b64decode(encoded, validate=True)
	except (ValueError, TypeError) as exc:
		raise DocumentParseError(f"{name}: 文件内容不是有效 Base64") from exc
	if len(raw) > MAX_DOCUMENT_BYTES:
		raise DocumentParseError(f"{name}: 文件超过 12 MB 限制")
	return name, raw


def _parse_docx(raw: bytes) -> str:
	try:
		with ZipFile(BytesIO(raw)) as archive:
			if sum(info.file_size for info in archive.infolist()) > MAX_DOCX_EXPANDED_BYTES:
				raise DocumentParseError("DOCX 解压后内容超过 32 MB 限制")
			names = [
				name for name in archive.namelist()
				if name == "word/document.xml"
				or name.startswith("word/header")
				or name.startswith("word/footer")
			]
			parts: list[str] = []
			for name in names:
				root = ElementTree.fromstring(archive.read(name))
				for paragraph in root.iter():
					if paragraph.tag.endswith("}p"):
						text = "".join(
							node.text or ""
							for node in paragraph.iter()
							if node.tag.endswith("}t")
						).strip()
						if text:
							parts.append(text)
	except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
		raise DocumentParseError("DOCX 文件损坏或格式不受支持") from exc
	return "\n".join(parts).strip()


def _decode_pdf_literal(value: bytes) -> str:
	value = re.sub(rb"\\([nrtbf()\\])", lambda match: {
		b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
		b"(": b"(", b")": b")", b"\\": b"\\",
	}[match.group(1)], value)
	value = re.sub(rb"\\([0-7]{1,3})", lambda match: bytes([int(match.group(1), 8) & 0xFF]), value)
	if value.startswith(b"\xfe\xff"):
		return value[2:].decode("utf-16-be", errors="ignore")
	return value.decode("latin-1", errors="ignore")


def _fallback_pdf_text(raw: bytes) -> str:
	parts: list[str] = []
	streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", raw, flags=re.S)
	for stream in streams:
		variants = [stream]
		try:
			variants.append(zlib.decompress(stream))
		except zlib.error:
			pass
		for content in variants:
			for match in re.finditer(rb"\((?:\\.|[^\)])*\)\s*Tj", content):
				text = _decode_pdf_literal(match.group(0)[1:match.group(0).rfind(b")")])
				if text.strip():
					parts.append(text.strip())
			for array in re.finditer(rb"\[(.*?)\]\s*TJ", content, flags=re.S):
				fragments = [
					_decode_pdf_literal(item)
					for item in re.findall(rb"\((?:\\.|[^\)])*\)", array.group(1))
				]
				text = "".join(fragments).strip()
				if text:
					parts.append(text)
	return "\n".join(parts).strip()


def _parse_pdf(raw: bytes) -> str:
	try:
		from pypdf import PdfReader
	except ImportError:
		text = _fallback_pdf_text(raw)
		if not text:
			raise DocumentParseError("PDF 无法提取文本；扫描版简历请先转换为可复制文本的 PDF")
		return text
	try:
		reader = PdfReader(BytesIO(raw))
		parts = [(page.extract_text() or "").strip() for page in reader.pages]
	except Exception:
		text = _fallback_pdf_text(raw)
		if not text:
			raise DocumentParseError("PDF 文件损坏、加密或无法提取文本")
		return text
	text = "\n\n".join(part for part in parts if part).strip()
	if not text:
		raise DocumentParseError("PDF 未包含可提取文本；扫描版简历暂不支持 OCR")
	return text


def parse_uploaded_document(entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
	"""Parse one browser-uploaded document into a resume-shaped mapping and source metadata."""
	if not isinstance(entry, dict):
		raise DocumentParseError("上传条目必须是对象")

	name = Path(str(entry.get("name") or "resume.json")).name
	payload = entry.get("payload")
	if isinstance(payload, dict):
		if len(json.dumps(payload, ensure_ascii=False)) > MAX_JSON_CHARS:
			raise DocumentParseError(f"{name}: JSON 简历内容过大")
		return payload, {"type": "web-upload", "filename": name, "format": "json"}

	name, raw = _read_payload(entry)
	extension = Path(name).suffix.lower()
	if extension not in SUPPORTED_EXTENSIONS:
		raise DocumentParseError(f"{name}: 不支持的文件类型")

	if extension == ".json":
		try:
			parsed = json.loads(_decode_bytes(raw))
		except json.JSONDecodeError as exc:
			raise DocumentParseError(f"{name}: JSON 格式错误") from exc
		if not isinstance(parsed, dict):
			raise DocumentParseError(f"{name}: JSON 顶层必须是对象")
		if len(json.dumps(parsed, ensure_ascii=False)) > MAX_JSON_CHARS:
			raise DocumentParseError(f"{name}: JSON 简历内容过大")
		return parsed, {"type": "web-upload", "filename": name, "format": "json"}

	if extension in {".txt", ".md"}:
		text = _decode_bytes(raw).strip()
	elif extension == ".docx":
		text = _parse_docx(raw)
	else:
		text = _parse_pdf(raw)

	if len(text) < 10:
		raise DocumentParseError(f"{name}: 未提取到足够的简历文本")
	truncated = len(text) > MAX_EXTRACTED_CHARS
	if truncated:
		text = text[:MAX_EXTRACTED_CHARS]
	return {
		"name": Path(name).stem,
		"raw_text": text,
		"source_document": {
			"filename": name, "format": extension.removeprefix("."), "truncated": truncated,
		},
	}, {
		"type": "web-upload",
		"filename": name,
		"format": extension.removeprefix("."),
	}
