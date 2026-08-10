"""Map recruiter persistence corruption to explicit Web integrity errors."""

from __future__ import annotations

import json
from typing import Any, Callable, cast

from boss_agent_cli.recruiter_ai import RecruiterAIError
from boss_agent_cli.web import controller as controller_module

_INSTALLED = False


def install_web_integrity(server_module: Any) -> None:
	"""Make corrupt recruiter files visible instead of silently omitting them from API responses."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	application_cls = server_module.RecruiterWebApplication
	original_get: Callable[..., Any] = application_cls.get

	def replies(self: Any, *, evaluation_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
		try:
			bounded_limit = max(1, min(int(limit), 500))
		except (TypeError, ValueError):
			bounded_limit = 100
		items: list[dict[str, Any]] = []
		for path in sorted(self.store.replies_dir.glob("reply_*.json"), reverse=True):
			try:
				payload = json.loads(path.read_text(encoding="utf-8"))
			except (OSError, json.JSONDecodeError) as exc:
				raise RecruiterAIError(f"回复草稿文件损坏: {path.name}") from exc
			if not isinstance(payload, dict):
				raise RecruiterAIError(f"回复草稿文件损坏: {path.name}")
			if evaluation_id and payload.get("evaluation_id") != evaluation_id:
				continue
			items.append(cast("dict[str, Any]", payload))
			if len(items) >= bounded_limit:
				break
		return items

	def get(self: Any, path: str, query: dict[str, list[str]]) -> Any:
		try:
			return original_get(self, path, query)
		except RecruiterAIError as exc:
			raise controller_module.WebConsoleError(
				"DATA_INTEGRITY_ERROR", str(exc), status=409,
			) from exc

	setattr(controller_cls, "replies", replies)
	setattr(application_cls, "get", get)
