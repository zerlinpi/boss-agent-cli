"""Version-aware freshness checks for recruiter autopilot sync state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

_INSTALLED = False


def install_autopilot_freshness(autopilot_module: Any) -> None:
	"""Only freshness-skip when the referenced evaluation still matches the saved job version."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True
	state_cls = autopilot_module.RecruiterAutopilotState
	original_is_fresh: Callable[..., bool] = state_cls.is_fresh

	# Generic `content` can occur in unrelated nested job-detail objects; only explicit JD fields
	# are safe enough for unattended auto-configuration.
	autopilot_module._JOB_DESCRIPTION_FIELDS = (
		"jobDescription",
		"jobDesc",
		"description",
		"postDescription",
		"post_description",
	)

	def is_fresh(self: Any, key: str, *, refresh_hours: int) -> bool:
		if not original_is_fresh(self, key, refresh_hours=refresh_hours):
			return False
		rows = self.payload.get("candidates")
		row = rows.get(key) if isinstance(rows, dict) else None
		if not isinstance(row, dict):
			return False
		evaluation_id = str(row.get("evaluation_id") or "").strip()
		job_key = key.split(":", 1)[0].strip()
		if not evaluation_id or not job_key:
			return False
		root = Path(self.path).parent
		evaluations_dir = (root / "evaluations").resolve()
		jobs_dir = (root / "jobs").resolve()
		evaluation_path = (evaluations_dir / f"{evaluation_id}.json").resolve()
		job_path = (jobs_dir / f"{job_key}.json").resolve()
		# The ledger is rebuildable/untrusted local state. Never allow a tampered key to make
		# freshness validation read outside the recruiter-ai data directories.
		if evaluation_path.parent != evaluations_dir or job_path.parent != jobs_dir:
			return False
		try:
			evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
			job = json.loads(job_path.read_text(encoding="utf-8"))
		except (OSError, json.JSONDecodeError, UnicodeDecodeError):
			return False
		if not isinstance(evaluation, dict) or not isinstance(job, dict):
			return False
		if str(evaluation.get("job_key") or "") != job_key:
			return False
		return (
			str(evaluation.get("jd_text") or "") == str(job.get("jd_text") or "")
			and str(evaluation.get("rubric_fingerprint") or "") == str(job.get("rubric_fingerprint") or "")
		)

	setattr(state_cls, "is_fresh", is_fresh)
