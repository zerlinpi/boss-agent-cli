"""Expose evaluation freshness metadata on read-only recruiter candidate details."""

from __future__ import annotations

from typing import Any, Callable

from boss_agent_cli.recruiter_ai_models import RecruiterAIError
from boss_agent_cli.recruiter_evaluation_freshness import evaluation_freshness
from boss_agent_cli.web import controller as controller_module

_INSTALLED = False


def install_candidate_freshness() -> None:
	"""Annotate candidate details without preventing inspection of historical evaluations."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	original: Callable[[Any, str], dict[str, Any]] = controller_cls.candidate_detail

	def candidate_detail(self: Any, evaluation_id: str) -> dict[str, Any]:
		record = original(self, evaluation_id)
		result = dict(record)
		try:
			result["freshness"] = evaluation_freshness(self.store, record, require_saved_job=True)
		except RecruiterAIError as exc:
			result["freshness"] = {
				"is_current": False,
				"reason": str(exc),
				"latest_evaluation_id": "",
				"job_exists": True,
				"job_current": False,
				"version_current": False,
			}
		return result

	setattr(controller_cls, "candidate_detail", candidate_detail)
