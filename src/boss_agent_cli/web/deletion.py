"""Local data lifecycle helpers for recruiter Web records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from boss_agent_cli.recruiter_ai import RecruiterAIError, RecruiterAIStore
from boss_agent_cli.recruiter_candidate_state import canonical_candidate_key


def _read_object(path: Path) -> dict[str, Any] | None:
	try:
		payload = json.loads(path.read_text(encoding="utf-8"))
	except (OSError, json.JSONDecodeError):
		return None
	return payload if isinstance(payload, dict) else None


def _delete_replies(store: RecruiterAIStore, evaluation_ids: set[str]) -> int:
	deleted = 0
	for path in store.replies_dir.glob("reply_*.json"):
		payload = _read_object(path)
		if payload is None or str(payload.get("evaluation_id") or "") not in evaluation_ids:
			continue
		path.unlink(missing_ok=True)
		deleted += 1
	return deleted


def delete_candidate_data(store: RecruiterAIStore, evaluation_id: str) -> dict[str, Any]:
	"""Delete all local evaluations and replies for one logical candidate."""
	target = store.get_evaluation(evaluation_id)
	candidate_key = canonical_candidate_key(target)
	if not candidate_key:
		raise RecruiterAIError(f"候选人评估缺少 candidate_key: {evaluation_id}")

	paths: list[Path] = []
	evaluation_ids: set[str] = set()
	for path in store.evaluations_dir.glob("eval_*.json"):
		payload = _read_object(path)
		if payload is None or canonical_candidate_key(payload) != candidate_key:
			continue
		paths.append(path)
		evaluation_ids.add(str(payload.get("id") or path.stem))

	if not paths:
		raise RecruiterAIError(f"未找到候选人评估数据: {evaluation_id}")
	for path in paths:
		path.unlink(missing_ok=True)
	return {
		"evaluation_id": evaluation_id,
		"candidate_key": candidate_key,
		"deleted_evaluation_ids": sorted(evaluation_ids),
		"evaluation_count": len(paths),
		"reply_count": _delete_replies(store, evaluation_ids),
	}


def delete_job_data(store: RecruiterAIStore, job_key: str) -> dict[str, Any]:
	"""Delete one job profile and all linked local evaluations and replies."""
	store.get_job(job_key)
	paths: list[Path] = []
	evaluation_ids: set[str] = set()
	for path in store.evaluations_dir.glob("eval_*.json"):
		payload = _read_object(path)
		if payload is None or str(payload.get("job_key") or "") != job_key:
			continue
		paths.append(path)
		evaluation_ids.add(str(payload.get("id") or path.stem))

	for path in paths:
		path.unlink(missing_ok=True)
	(store.jobs_dir / f"{job_key}.json").unlink(missing_ok=True)
	return {
		"job_key": job_key,
		"deleted_evaluation_ids": sorted(evaluation_ids),
		"evaluation_count": len(paths),
		"reply_count": _delete_replies(store, evaluation_ids),
	}
