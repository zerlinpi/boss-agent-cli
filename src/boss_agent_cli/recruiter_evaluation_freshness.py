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


def evaluation_freshness(
	store: Any,
	record: dict[str, Any],
	*,
	require_saved_job: bool = False,
) -> dict[str, Any]:
	"""Return explainable freshness metadata without rejecting read-only inspection."""
	evaluation_id = str(record.get("id") or "")
	job_key = str(record.get("job_key") or "")
	result: dict[str, Any] = {
		"is_current": False,
		"reason": "",
		"latest_evaluation_id": "",
		"job_exists": False,
		"job_current": False,
		"version_current": False,
	}
	if not evaluation_id or not job_key:
		result["reason"] = "评估记录缺少岗位或记录标识，请重新评估"
		return result

	job = get_saved_job_optional(store, job_key)
	result["job_exists"] = job is not None
	if job is None and require_saved_job:
		result["reason"] = "岗位配置已不存在，请重新创建岗位并筛选候选人"
		return result

	if isinstance(job, dict):
		if str(record.get("jd_text") or "") != str(job.get("jd_text") or ""):
			result["reason"] = "该评估基于旧 JD，请重新筛选候选人"
			return result
		if str(record.get("rubric_fingerprint") or "") != str(job.get("rubric_fingerprint") or ""):
			result["reason"] = "该评估基于旧评分规则，请重新筛选候选人"
			return result
	result["job_current"] = True

	latest = store.latest_by_candidate(job_key=job_key)
	current = latest.get(canonical_candidate_key(record))
	if isinstance(current, dict):
		result["latest_evaluation_id"] = str(current.get("id") or "")
	if not isinstance(current, dict) or str(current.get("id") or "") != evaluation_id:
		result["reason"] = "该候选人已有更新的评估版本，请使用最新结果"
		return result

	result["version_current"] = True
	result["is_current"] = True
	return result


def require_current_evaluation(
	store: Any,
	record: dict[str, Any],
	*,
	require_saved_job: bool = False,
) -> None:
	"""Reject superseded or old-job evaluations before downstream model actions."""
	freshness = evaluation_freshness(store, record, require_saved_job=require_saved_job)
	if not freshness["is_current"]:
		raise RecruiterAIError(str(freshness["reason"] or "该评估已过期，请重新筛选候选人"))
