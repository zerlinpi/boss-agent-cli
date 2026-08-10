"""Strict preflight validation for destructive and state-changing Web writes."""

from __future__ import annotations

from typing import Any, Callable

from boss_agent_cli.web import controller as controller_module

_INSTALLED = False


def _text(value: Any, *, label: str, maximum: int, allow_empty: bool = False) -> str:
	if not isinstance(value, str):
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 必须是字符串")
	text = value.strip()
	if not allow_empty and not text:
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 不能为空")
	if len(text) > maximum:
		raise controller_module.WebConsoleError("INVALID_PARAM", f"{label} 过长，最多 {maximum} 字符")
	return text


def install_write_input_safety(server_module: Any) -> None:
	"""Reject ambiguous destructive flags and structured state values before routing writes."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	application_cls = server_module.RecruiterWebApplication
	original_post: Callable[..., Any] = application_cls.post

	def post(self: Any, path: str, payload: dict[str, Any]) -> Any:
		clean = dict(payload)

		if path == "/api/jobs" and "_delete" in clean:
			delete_flag = clean.get("_delete")
			if not isinstance(delete_flag, bool):
				raise controller_module.WebConsoleError(
					"INVALID_PARAM", "_delete 必须是布尔值；只有 true 才表示永久删除"
				)
			clean["_delete"] = delete_flag

		if path == "/api/settings/mode" and "mode" in clean:
			clean["mode"] = _text(clean.get("mode"), label="运行模式", maximum=32)

		if path == "/api/candidates/bulk-status":
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

		if path.startswith("/api/candidates/") and path.endswith("/status"):
			clean["status"] = _text(clean.get("status"), label="候选人状态", maximum=64)
			clean["note"] = _text(clean.get("note", ""), label="候选人备注", maximum=5000, allow_empty=True)

		return original_post(self, path, clean)

	setattr(application_cls, "post", post)
