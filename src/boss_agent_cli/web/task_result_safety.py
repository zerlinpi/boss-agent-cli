"""Persistence contract for asynchronous recruiter Web task results."""

from __future__ import annotations

import json
from typing import Any, Callable


def install_task_result_safety(tasks_module: Any) -> None:
	"""Fail tasks cleanly when a worker returns data SQLite JSON storage cannot persist."""
	task_cls = tasks_module.TaskManager
	if getattr(task_cls, "_boss_task_result_safety_installed", False):
		return
	original_submit: Callable[..., dict[str, Any]] = task_cls.submit

	def submit(
		self: Any,
		kind: str,
		fn: Callable[[Callable[[int, str], None]], dict[str, Any]],
		*,
		metadata: dict[str, Any] | None = None,
	) -> dict[str, Any]:
		def safe_fn(progress: Callable[[int, str], None]) -> dict[str, Any]:
			result = fn(progress)
			if not isinstance(result, dict):
				raise TypeError("后台任务结果必须是 JSON 对象")
			try:
				json.dumps(result, ensure_ascii=False, allow_nan=False)
			except (TypeError, ValueError) as exc:
				raise TypeError("后台任务结果包含无法持久化的 JSON 数据") from exc
			return result

		if metadata is not None:
			if not isinstance(metadata, dict):
				raise TypeError("后台任务 metadata 必须是 JSON 对象")
			try:
				json.dumps(metadata, ensure_ascii=False, allow_nan=False)
			except (TypeError, ValueError) as exc:
				raise TypeError("后台任务 metadata 包含无法持久化的 JSON 数据") from exc
		return original_submit(self, kind, safe_fn, metadata=metadata)

	setattr(task_cls, "submit", submit)
	setattr(task_cls, "_boss_task_result_safety_installed", True)
