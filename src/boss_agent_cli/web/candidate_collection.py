"""Candidate collection metadata for large recruiter pipelines."""

from __future__ import annotations

from typing import Any, Callable

from boss_agent_cli.web import controller as controller_module

_INSTALLED = False


def install_candidate_collection_metadata() -> None:
	"""Expose whether the requested candidate list is only a prefix of the current job pool."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	original: Callable[..., dict[str, Any]] = controller_cls.candidates

	def candidates(self: Any, job_key: str, *, top: int = 200) -> dict[str, Any]:
		result = original(self, job_key, top=top)
		raw_items = result.get("items")
		items = raw_items if isinstance(raw_items, list) else []
		raw_report = result.get("report")
		report = raw_report if isinstance(raw_report, dict) else {}
		total = int(report.get("total_candidates") or len(items))
		result["returned_count"] = len(items)
		result["total_count"] = total
		result["truncated"] = total > len(items)
		result["requested_top"] = max(0, int(top))
		return result

	setattr(controller_cls, "candidates", candidates)
