"""Strict preflight validation for destructive and state-changing Web writes."""

from __future__ import annotations

import math
import re
from typing import Any, Callable

from boss_agent_cli.web import controller as controller_module
from boss_agent_cli.web.upload_policy import MAX_LOCAL_BATCH_BYTES, estimated_document_bytes

_CONTROLLER_INSTALLED = False
_SERVER_INSTALLED = False
_INTEGER_TEXT_RE = re.compile(r"^[+-]?\d+$")
_MAX_JD_CHARS = 100_000


def _text(value: Any, *, label: str, maximum: int, allow_empty: bool = False) -> str:
	if not isinstance(value, str):
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 必须是字符串")
	text = value.strip()
	if not allow_empty and not text:
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 不能为空")
	if len(text) > maximum:
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 过长，最多 {maximum} 字符")
	return text


def _integer(value: Any, *, label: str, default: int, minimum: int, maximum: int) -> int:
	if value in (None, ""):
		return default
	if isinstance(value, bool):
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 必须是整数")
	if isinstance(value, int):
		parsed = value
	elif isinstance(value, float):
		if not math.isfinite(value) or not value.is_integer():
			raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 必须是整数")
		parsed = int(value)
	elif isinstance(value, str) and _INTEGER_TEXT_RE.fullmatch(value.strip()):
		parsed = int(value.strip())
	else:
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 必须是整数")
	if not minimum <= parsed <= maximum:
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 必须在 {minimum}-{maximum} 之间")
	return parsed


def _boolean(value: Any, *, label: str, default: bool = False) -> bool:
	if value is None:
		return default
	if isinstance(value, bool):
		return value
	raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 必须是布尔值")


def _normalize_bulk_payload(payload: dict[str, Any]) -> dict[str, Any]:
	clean = dict(payload)
	identifiers = clean.get("evaluation_ids")
	if not isinstance(identifiers, list) or not identifiers:
		raise controller_module.WebConsoleError("INVALID_BULK_INPUT", "请选择至少一位候选人")
	if len(identifiers) > 100:
		raise controller_module.WebConsoleError("INVALID_BULK_INPUT", "单次最多操作 100 位候选人")
	unique: list[str] = []
	seen: set[str] = set()
	for value in identifiers:
		identifier = _text(value, label="候选人评估 ID", maximum=160)
		if identifier not in seen:
			seen.add(identifier)
			unique.append(identifier)
	clean["evaluation_ids"] = unique
	clean["status"] = _text(clean.get("status"), label="候选人状态", maximum=64)
	clean["note"] = _text(clean.get("note", ""), label="候选人备注", maximum=5000, allow_empty=True)
	return clean


def _preflight_async(path: str, clean: dict[str, Any]) -> None:
	if path == "/api/jobs/analyze":
		clean["jd_text"] = _text(clean.get("jd_text"), label="JD", maximum=_MAX_JD_CHARS)
		return

	if path == "/api/screen/local":
		clean["job_key"] = _text(clean.get("job_key"), label="岗位标识", maximum=128)
		entries = clean.get("documents", clean.get("resumes"))
		if not isinstance(entries, list) or not entries:
			raise controller_module.WebConsoleError("INVALID_SCREEN_INPUT", "请选择并上传至少一份简历")
		if len(entries) > 100:
			raise controller_module.WebConsoleError("INVALID_SCREEN_INPUT", "单次最多上传 100 份简历")
		if any(not isinstance(entry, dict) for entry in entries):
			raise controller_module.WebConsoleError("INVALID_SCREEN_INPUT", "每个简历条目都必须是 JSON 对象")
		if sum(estimated_document_bytes(entry) for entry in entries) > MAX_LOCAL_BATCH_BYTES:
			raise controller_module.WebConsoleError(
				"PAYLOAD_TOO_LARGE",
				"单次简历批次解码后不能超过 40 MB，请拆分后重试",
				status=413,
			)
		clean["force"] = _boolean(clean.get("force"), label="force")
		return

	if path == "/api/screen/boss":
		clean["job_key"] = _text(clean.get("job_key"), label="岗位标识", maximum=128)
		clean["job_id"] = _text(clean.get("job_id"), label="BOSS 职位 ID", maximum=256)
		clean["pages"] = _integer(clean.get("pages"), label="pages", default=1, minimum=1, maximum=10)
		clean["limit"] = _integer(clean.get("limit"), label="limit", default=30, minimum=1, maximum=100)
		clean["draft_top"] = _integer(
			clean.get("draft_top"), label="draft_top", default=0, minimum=0, maximum=20
		)
		clean["force"] = _boolean(clean.get("force"), label="force")
		clean["include_chat"] = _boolean(clean.get("include_chat"), label="include_chat")


def install_controller_write_input_safety() -> None:
	"""Apply the same destructive/state validation to direct controller callers."""
	global _CONTROLLER_INSTALLED
	if _CONTROLLER_INSTALLED:
		return
	_CONTROLLER_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	original_save_job: Callable[..., dict[str, Any]] = controller_cls.save_job
	original_mark: Callable[..., dict[str, Any]] = controller_cls.mark_candidate
	original_bulk: Callable[..., dict[str, Any]] = controller_cls.bulk_mark_candidates

	def save_job(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
		clean = dict(payload)
		if "_delete" in clean:
			clean["_delete"] = _boolean(clean.get("_delete"), label="_delete")
		return original_save_job(self, clean)

	def mark_candidate(self: Any, evaluation_id: str, status: str, note: str = "") -> dict[str, Any]:
		clean_status = _text(status, label="候选人状态", maximum=64)
		clean_note = _text(note, label="候选人备注", maximum=5000, allow_empty=True)
		return original_mark(self, evaluation_id, clean_status, note=clean_note)

	def bulk_mark_candidates(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
		return original_bulk(self, _normalize_bulk_payload(payload))

	setattr(controller_cls, "save_job", save_job)
	setattr(controller_cls, "mark_candidate", mark_candidate)
	setattr(controller_cls, "bulk_mark_candidates", bulk_mark_candidates)


def install_write_input_safety(server_module: Any) -> None:
	"""Reject ambiguous or malformed writes before routing or background task creation."""
	global _SERVER_INSTALLED
	if _SERVER_INSTALLED:
		return
	_SERVER_INSTALLED = True

	application_cls = server_module.RecruiterWebApplication
	original_post: Callable[..., Any] = application_cls.post

	def post(self: Any, path: str, payload: dict[str, Any]) -> Any:
		clean = dict(payload)
		_preflight_async(path, clean)

		if path == "/api/jobs" and "_delete" in clean:
			clean["_delete"] = _boolean(clean.get("_delete"), label="_delete")

		if path == "/api/settings/mode" and "mode" in clean:
			clean["mode"] = _text(clean.get("mode"), label="运行模式", maximum=32)

		if path == "/api/candidates/bulk-status":
			clean = _normalize_bulk_payload(clean)

		if path.startswith("/api/candidates/") and path.endswith("/status"):
			clean["status"] = _text(clean.get("status"), label="候选人状态", maximum=64)
			clean["note"] = _text(clean.get("note", ""), label="候选人备注", maximum=5000, allow_empty=True)

		return original_post(self, path, clean)

	setattr(application_cls, "post", post)
