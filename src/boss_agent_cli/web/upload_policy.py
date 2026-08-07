"""Server-side batch upload policy for recruiter resume screening."""

from __future__ import annotations

import json
from typing import Any, Callable

from boss_agent_cli.web import controller as controller_module

_INSTALLED = False
MAX_LOCAL_BATCH_BYTES = 40 * 1024 * 1024


def _base64_decoded_size(encoded: str) -> int:
	length = len(encoded)
	padding = 0
	if encoded.endswith("=="):
		padding = 2
	elif encoded.endswith("="):
		padding = 1
	return max(0, (length * 3) // 4 - padding)


def _estimated_document_bytes(entry: Any) -> int:
	if not isinstance(entry, dict):
		return 0
	encoded = entry.get("content_base64")
	if isinstance(encoded, str):
		return _base64_decoded_size(encoded)
	payload = entry.get("payload")
	if isinstance(payload, dict):
		try:
			return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
		except (TypeError, ValueError):
			return 0
	return 0


def install_upload_policy() -> None:
	"""Reject oversized local batches before any document is decoded or parsed."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	original_screen_local: Callable[..., dict[str, Any]] = controller_cls.screen_local

	def screen_local(self: Any, payload: dict[str, Any], *, progress: Any = None) -> dict[str, Any]:
		entries = payload.get("documents", payload.get("resumes"))
		if isinstance(entries, list):
			total = sum(_estimated_document_bytes(entry) for entry in entries)
			if total > MAX_LOCAL_BATCH_BYTES:
				raise controller_module.WebConsoleError(
					"PAYLOAD_TOO_LARGE",
					"单次简历批次解码后不能超过 40 MB，请拆分后重试",
					status=413,
				)
		return original_screen_local(self, payload, progress=progress)

	setattr(controller_cls, "screen_local", screen_local)
