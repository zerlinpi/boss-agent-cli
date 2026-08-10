"""Local data lifecycle helpers for recruiter Web records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from boss_agent_cli.recruiter_ai import RecruiterAIError, RecruiterAIStore
from boss_agent_cli.recruiter_candidate_state import canonical_candidate_key


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
	try:
		payload = json.loads(path.read_text(encoding="utf-8"))
	except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
		raise RecruiterAIError(f"{label}损坏，无法确认完整删除范围: {path.name}") from exc
	if not isinstance(payload, dict):
		raise RecruiterAIError(f"{label}损坏，无法确认完整删除范围: {path.name}")
	return payload


def _reply_paths(store: RecruiterAIStore, evaluation_ids: set[str]) -> list[Path]:
	paths: list[Path] = []
	for path in store.replies_dir.glob("reply_*.json"):
		payload = _read_object(path, label="回复草稿文件")
		if str(payload.get("evaluation_id") or "") in evaluation_ids:
			paths.append(path)
	return paths


def _delete_paths(paths: list[Path], *, label: str) -> int:
	deleted = 0
	for path in paths:
		try:
			path.unlink(missing_ok=True)
		except OSError as exc:
			raise RecruiterAIError(f"删除{label}失败: {path.name}") from exc
		deleted += 1
	return deleted


def delete_candidate_data(store: RecruiterAIStore, evaluation_id: str) -> dict[str, Any]:
	"""Delete every version of one logical candidate within the target evaluation's job."""
	target = store.get_evaluation(evaluation_id)
	candidate_key = canonical_candidate_key(target)
	job_key = str(target.get("job_key") or "")
	if not candidate_key:
		raise RecruiterAIError(f"候选人评估缺少 candidate_key: {evaluation_id}")
	if not job_key:
		raise RecruiterAIError(f"候选人评估缺少 job_key: {evaluation_id}")

	# Preflight every evaluation/reply file before mutating anything. A corrupt file cannot be safely
	# classified as related or unrelated, so claiming a complete privacy deletion would be false.
	evaluation_paths: list[Path] = []
	evaluation_ids: set[str] = set()
	for path in store.evaluations_dir.glob("eval_*.json"):
		payload = _read_object(path, label="候选人评估文件")
		if str(payload.get("job_key") or "") != job_key:
			continue
		if canonical_candidate_key(payload) != candidate_key:
			continue
		evaluation_paths.append(path)
		evaluation_ids.add(str(payload.get("id") or path.stem))

	if not evaluation_paths:
		raise RecruiterAIError(f"未找到候选人评估数据: {evaluation_id}")
	reply_paths = _reply_paths(store, evaluation_ids)

	reply_count = _delete_paths(reply_paths, label="回复草稿")
	_delete_paths(evaluation_paths, label="候选人评估")
	return {
		"evaluation_id": evaluation_id,
		"job_key": job_key,
		"candidate_key": candidate_key,
		"deleted_evaluation_ids": sorted(evaluation_ids),
		"evaluation_count": len(evaluation_paths),
		"reply_count": reply_count,
	}


def delete_job_data(store: RecruiterAIStore, job_key: str) -> dict[str, Any]:
	"""Delete one job profile and all linked local evaluations and replies."""
	store.get_job(job_key)

	# Strict preflight avoids deleting the known files while silently leaving an unreadable record
	# that might still contain data for this job.
	evaluation_paths: list[Path] = []
	evaluation_ids: set[str] = set()
	for path in store.evaluations_dir.glob("eval_*.json"):
		payload = _read_object(path, label="候选人评估文件")
		if str(payload.get("job_key") or "") != job_key:
			continue
		evaluation_paths.append(path)
		evaluation_ids.add(str(payload.get("id") or path.stem))
	reply_paths = _reply_paths(store, evaluation_ids)

	reply_count = _delete_paths(reply_paths, label="回复草稿")
	_delete_paths(evaluation_paths, label="候选人评估")
	job_path = store.jobs_dir / f"{job_key}.json"
	try:
		job_path.unlink(missing_ok=True)
	except OSError as exc:
		raise RecruiterAIError(f"删除岗位配置失败: {job_key}") from exc
	return {
		"job_key": job_key,
		"deleted_evaluation_ids": sorted(evaluation_ids),
		"evaluation_count": len(evaluation_paths),
		"reply_count": reply_count,
	}
