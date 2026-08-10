"""Strict integrity checks for persisted recruiter records."""

from __future__ import annotations

import json
from typing import Any, Callable, cast


_INSTALLED = False


def install_store_integrity(store_cls: type[Any], error_cls: type[Exception]) -> None:
	"""Reject corrupt job/evaluation JSON instead of silently hiding records from lists."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	original_list_jobs: Callable[..., list[dict[str, Any]]] = store_cls.list_jobs
	original_list_evaluations: Callable[..., list[dict[str, Any]]] = store_cls.list_evaluations

	def list_jobs(self: Any) -> list[dict[str, Any]]:
		jobs: list[dict[str, Any]] = []
		for path in sorted(self.jobs_dir.glob("*.json")):
			try:
				payload = json.loads(path.read_text(encoding="utf-8"))
			except (OSError, json.JSONDecodeError) as exc:
				raise error_cls(f"岗位配置文件损坏: {path.name}") from exc
			if not isinstance(payload, dict):
				raise error_cls(f"岗位配置文件损坏: {path.name}")
			jobs.append(cast("dict[str, Any]", payload))
		return jobs

	def list_evaluations(self: Any, *, job_key: str | None = None) -> list[dict[str, Any]]:
		records: list[dict[str, Any]] = []
		for path in self.evaluations_dir.glob("eval_*.json"):
			try:
				payload = json.loads(path.read_text(encoding="utf-8"))
			except (OSError, json.JSONDecodeError) as exc:
				raise error_cls(f"评估文件损坏: {path.name}") from exc
			if not isinstance(payload, dict):
				raise error_cls(f"评估文件损坏: {path.name}")
			if job_key is not None and payload.get("job_key") != job_key:
				continue
			records.append(cast("dict[str, Any]", payload))
		return records

	setattr(store_cls, "_boss_integrity_original_list_jobs", original_list_jobs)
	setattr(store_cls, "_boss_integrity_original_list_evaluations", original_list_evaluations)
	setattr(store_cls, "list_jobs", list_jobs)
	setattr(store_cls, "list_evaluations", list_evaluations)
