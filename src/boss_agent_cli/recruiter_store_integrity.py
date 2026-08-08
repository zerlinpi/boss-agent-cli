"""Fail-closed integrity checks for recruiter evaluation persistence."""

from __future__ import annotations

import json
from typing import Any

from boss_agent_cli.recruiter_ai_models import RecruiterAIError

_INSTALLED = False


def _read_evaluation(path: Any) -> dict[str, Any]:
	try:
		payload = json.loads(path.read_text(encoding="utf-8"))
	except (OSError, UnicodeError, json.JSONDecodeError) as exc:
		raise RecruiterAIError(f"评估文件损坏: {path.name}") from exc
	if not isinstance(payload, dict):
		raise RecruiterAIError(f"评估文件损坏: {path.name}")
	record_id = str(payload.get("id") or "")
	if not record_id or record_id != path.stem:
		raise RecruiterAIError(f"评估文件标识不一致: {path.name}")
	return payload


def install_evaluation_integrity(store_cls: type[Any]) -> None:
	"""Reject corrupt evaluation history instead of silently falling back to older scores."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	def list_evaluations(self: Any, *, job_key: str | None = None) -> list[dict[str, Any]]:
		items: list[dict[str, Any]] = []
		for path in sorted(self.evaluations_dir.glob("eval_*.json")):
			payload = _read_evaluation(path)
			if job_key is None or payload.get("job_key") == job_key:
				items.append(payload)
		return items

	def get_evaluation(self: Any, record_id: str) -> dict[str, Any]:
		from boss_agent_cli.recruiter_ai_store import _safe_storage_key

		safe_id = _safe_storage_key(record_id, label="evaluation_id", max_length=160)
		path = self.evaluations_dir / f"{safe_id}.json"
		if not path.is_file():
			raise RecruiterAIError(f"评估记录不存在: {safe_id}")
		return _read_evaluation(path)

	setattr(store_cls, "list_evaluations", list_evaluations)
	setattr(store_cls, "get_evaluation", get_evaluation)
