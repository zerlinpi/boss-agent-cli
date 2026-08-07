"""Model-input isolation for AI-assisted job profile analysis."""

from __future__ import annotations

from typing import Any, Callable

from boss_agent_cli.recruiter_ai import redact_contact_text
from boss_agent_cli.web import controller as controller_module

_INSTALLED = False


def install_job_analysis_safety() -> None:
	"""Sanitize JD text before the job-analysis model sees it without altering the locally saved JD."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	original_analyze: Callable[..., dict[str, Any]] = controller_cls.analyze_job

	def analyze_job(self: Any, payload: dict[str, Any], *, progress: Any = None) -> dict[str, Any]:
		safe_payload = dict(payload)
		jd_text = payload.get("jd_text")
		if isinstance(jd_text, str):
			safe_payload["jd_text"] = redact_contact_text(jd_text)
		return original_analyze(self, safe_payload, progress=progress)

	setattr(controller_cls, "analyze_job", analyze_job)
