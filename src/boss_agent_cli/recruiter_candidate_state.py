"""Preserve recruiter-owned candidate state across AI re-evaluation versions."""

from __future__ import annotations

from typing import Any, Callable

import boss_agent_cli.recruiter_ai_store as store_module
from boss_agent_cli.recruiter_ai_models import CANDIDATE_STATUSES

_INSTALLED = False


def canonical_candidate_key(record: dict[str, Any]) -> str:
	"""Return the current logical identity for current and legacy evaluation records."""
	resume = record.get("resume")
	source = record.get("source")
	if isinstance(resume, dict):
		try:
			return store_module.candidate_key(resume, source if isinstance(source, dict) else None)
		except (TypeError, ValueError):
			pass
	return str(record.get("candidate_key") or record.get("id") or "")


def install_candidate_state_retention() -> None:
	"""Treat status/note as recruiter state that survives new AI evaluation versions."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	store_cls = store_module.RecruiterAIStore
	original_save: Callable[..., dict[str, Any]] = store_cls.save_evaluation

	def latest_by_candidate(self: Any, *, job_key: str) -> dict[str, dict[str, Any]]:
		latest: dict[str, dict[str, Any]] = {}
		for record in self.list_evaluations(job_key=job_key):
			key = canonical_candidate_key(record)
			current = latest.get(key)
			if current is None or str(record.get("created_at", "")) > str(current.get("created_at", "")):
				latest[key] = record
		return latest

	def save_evaluation(self: Any, **kwargs: Any) -> dict[str, Any]:
		job_key = str(kwargs.get("job_key") or "")
		resume = kwargs.get("resume")
		source = kwargs.get("source")
		previous: dict[str, Any] | None = None
		if job_key and isinstance(resume, dict):
			try:
				key = store_module.candidate_key(resume, source if isinstance(source, dict) else None)
				previous = self.latest_by_candidate(job_key=job_key).get(key)
			except (TypeError, ValueError):
				previous = None

		record = original_save(self, **kwargs)
		if not isinstance(previous, dict):
			return record
		status = str(previous.get("status") or "new")
		if status not in CANDIDATE_STATUSES:
			return record
		note = str(previous.get("status_note") or "")
		# Recruiter notes are candidate-level state too. A note entered while the candidate is still
		# in the default `new` stage must not disappear just because a new AI evaluation version is saved.
		if status == "new" and not note:
			return record
		return self.set_status(str(record.get("id") or ""), status, note=note)

	setattr(store_cls, "latest_by_candidate", latest_by_candidate)
	setattr(store_cls, "save_evaluation", save_evaluation)
