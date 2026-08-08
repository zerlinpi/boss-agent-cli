"""Shared freshness checks for actions that must use the latest recruiter evaluation."""

from __future__ import annotations

from typing import Any

from boss_agent_cli.recruiter_candidate_state import canonical_candidate_key
from boss_agent_cli.recruiter_ai_models import RecruiterAIError
from boss_agent_cli.recruiter_ai_store import _safe_storage_key


def get_saved_job_optional(store: Any, job_key: str) -> dict[str, Any] | None:
	"""Return a saved job, but never disguise invalid/corrupt job data as ad-hoc mode."""
	safe_key = _safe_storage_key(job_key, label="job_key", max_length=128)
	path = store.jobs_dir / f"{safe_key}.json"
	if not path.is_file():
		return None
	job = store.get_job(safe_key)
	if not isinstance(job, dict):
		raise RecruiterAIError(f"岗位配置损坏: {safe_key}")
	return job


def require_current_evaluation(
	store: Any,
	record: dict[str, Any],
	*,
	require_saved_job: bool = False,
) -> None:
	"""Reject superseded or old-job evaluations before downstream model actions."""
	evaluation_id = str(record.get("id") or "")
	job_key = str(record.get("job_key") or "")
	if not evaluation_id or not job_key:
		raise RecruiterAIError("评估记录缺少岗位或记录标识，请重新评估")

	job = get_saved_job_optional(store, job_key)
	if job is None and require_saved_job:
		raise RecruiterAIError("岗位配置已不存在，请重新创建岗位并筛选候选人")

	if isinstance(job, dict):
		if str(record.get("jd_text") or "") != str(job.get("jd_text") or ""):
			raise RecruiterAIError("该评估基于旧 JD，请重新筛选候选人")
		if str(record.get("rubric_fingerprint") or "") != str(job.get("rubric_fingerprint") or ""):
			raise RecruiterAIError("该评估基于旧评分规则，请重新筛选候选人")

	latest = store.latest_by_candidate(job_key=job_key)
	current = latest.get(canonical_candidate_key(record))
	if not isinstance(current, dict) or str(current.get("id") or "") != evaluation_id:
		raise RecruiterAIError("该候选人已有更新的评估版本，请使用最新结果")
