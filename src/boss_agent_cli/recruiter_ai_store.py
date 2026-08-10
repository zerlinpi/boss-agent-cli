"""Auditable local persistence for recruiter AI workflows."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, cast
from uuid import uuid4

from boss_agent_cli.recruiter_ai_models import (
	CANDIDATE_STATUSES,
	RECOMMENDATIONS,
	SCHEMA_VERSION,
	RecruiterAIError,
	candidate_key,
	candidate_name,
	normalize_rubric,
	redact_contact_text,
	resume_fingerprint,
	rubric_fingerprint,
)

_WINDOWS_DEVICE_NAME = re.compile(r"^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$", re.IGNORECASE)
_WINDOWS_INVALID_CHARS = set('<>:"/\\|?*')


def _utc_now() -> str:
	return datetime.now(timezone.utc).isoformat()


def _restrict_permissions(path: Path, mode: int) -> None:
	"""Best-effort local permission hardening without making Windows startup brittle."""
	try:
		path.chmod(mode)
	except OSError:
		pass


def _safe_storage_key(value: str, *, label: str, max_length: int = 160) -> str:
	"""Reject traversal and cross-platform-invalid filenames while retaining readable Unicode keys."""
	key = value.strip()
	if not key:
		raise RecruiterAIError(f"{label} 不能为空")
	if len(key) > max_length:
		raise RecruiterAIError(f"{label} 过长")
	if key in {".", ".."} or key.endswith("."):
		raise RecruiterAIError(f"{label} 包含非法路径字符")
	if any(char in _WINDOWS_INVALID_CHARS or ord(char) < 32 for char in key):
		raise RecruiterAIError(f"{label} 包含非法路径字符")
	if _WINDOWS_DEVICE_NAME.fullmatch(key):
		raise RecruiterAIError(f"{label} 使用了 Windows 保留文件名")
	return key


def _finite_sort_value(value: Any) -> float:
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		return -1.0
	number = float(value)
	return number if math.isfinite(number) else -1.0


class RecruiterAIStore:
	"""Persist job profiles, evaluations, candidate state, and reply drafts."""

	def __init__(self, data_dir: Path):
		self.root = data_dir / "recruiter-ai"
		self.root.mkdir(parents=True, exist_ok=True)
		_restrict_permissions(self.root, 0o700)
		self.jobs_dir = self.root / "jobs"
		self.evaluations_dir = self.root / "evaluations"
		self.replies_dir = self.root / "replies"
		for directory in (self.jobs_dir, self.evaluations_dir, self.replies_dir):
			directory.mkdir(parents=True, exist_ok=True)
			_restrict_permissions(directory, 0o700)

	@staticmethod
	def _new_id(prefix: str) -> str:
		stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
		return f"{prefix}_{stamp}_{uuid4().hex[:8]}"

	@staticmethod
	def _write(path: Path, payload: dict[str, Any]) -> None:
		# A unique temporary file prevents concurrent writes to the same record from racing on one `.tmp` path.
		temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
		try:
			temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
			_restrict_permissions(temporary, 0o600)
			temporary.replace(path)
			_restrict_permissions(path, 0o600)
		finally:
			temporary.unlink(missing_ok=True)

	def save_job(
		self,
		*,
		job_key: str,
		jd_text: str,
		rubric: dict[str, Any] | None = None,
		metadata: dict[str, Any] | None = None,
	) -> dict[str, Any]:
		job_key = _safe_storage_key(job_key, label="job_key", max_length=128)
		normalized_rubric = normalize_rubric(rubric)
		record = {
			"schema_version": SCHEMA_VERSION,
			"job_key": job_key,
			"updated_at": _utc_now(),
			"jd_text": jd_text,
			"rubric": normalized_rubric,
			"rubric_fingerprint": rubric_fingerprint(normalized_rubric),
			"metadata": metadata or {},
		}
		self._write(self.jobs_dir / f"{job_key}.json", record)
		return record

	def get_job(self, job_key: str) -> dict[str, Any]:
		job_key = _safe_storage_key(job_key, label="job_key", max_length=128)
		path = self.jobs_dir / f"{job_key}.json"
		if not path.is_file():
			raise RecruiterAIError(f"岗位配置不存在: {job_key}")
		try:
			payload = json.loads(path.read_text(encoding="utf-8"))
		except (OSError, json.JSONDecodeError) as exc:
			raise RecruiterAIError(f"岗位配置损坏: {job_key}") from exc
		if not isinstance(payload, dict):
			raise RecruiterAIError(f"岗位配置损坏: {job_key}")
		return cast("dict[str, Any]", payload)

	def list_jobs(self) -> list[dict[str, Any]]:
		jobs: list[dict[str, Any]] = []
		for path in sorted(self.jobs_dir.glob("*.json")):
			try:
				payload = json.loads(path.read_text(encoding="utf-8"))
			except (OSError, json.JSONDecodeError):
				continue
			if isinstance(payload, dict):
				jobs.append(cast("dict[str, Any]", payload))
		return jobs

	def save_evaluation(
		self,
		*,
		job_key: str,
		jd_text: str,
		resume: dict[str, Any],
		evaluation: dict[str, Any],
		source: dict[str, Any] | None = None,
		rubric: dict[str, Any] | None = None,
	) -> dict[str, Any]:
		source = source or {"type": "local"}
		normalized_rubric = normalize_rubric(rubric)
		record_id = self._new_id("eval")
		record = {
			"schema_version": SCHEMA_VERSION,
			"id": record_id,
			"created_at": _utc_now(),
			"updated_at": _utc_now(),
			"job_key": job_key,
			"candidate_key": candidate_key(resume, source),
			"candidate_name": candidate_name(resume),
			"resume_fingerprint": resume_fingerprint(resume),
			"rubric_fingerprint": rubric_fingerprint(normalized_rubric),
			"jd_text": jd_text,
			"rubric": normalized_rubric,
			"resume": resume,
			"evaluation": evaluation,
			"source": source,
			"status": "new",
		}
		self._write(self.evaluations_dir / f"{record_id}.json", record)
		return record

	def get_evaluation(self, record_id: str) -> dict[str, Any]:
		record_id = _safe_storage_key(record_id, label="评估记录 ID")
		path = self.evaluations_dir / f"{record_id}.json"
		if not path.is_file():
			raise RecruiterAIError(f"评估记录不存在: {record_id}")
		try:
			payload = json.loads(path.read_text(encoding="utf-8"))
		except (OSError, json.JSONDecodeError) as exc:
			raise RecruiterAIError(f"评估记录损坏: {record_id}") from exc
		if not isinstance(payload, dict):
			raise RecruiterAIError(f"评估记录损坏: {record_id}")
		return cast("dict[str, Any]", payload)

	def list_evaluations(self, *, job_key: str | None = None) -> list[dict[str, Any]]:
		records: list[dict[str, Any]] = []
		for path in self.evaluations_dir.glob("eval_*.json"):
			try:
				payload = json.loads(path.read_text(encoding="utf-8"))
			except (OSError, json.JSONDecodeError):
				continue
			if not isinstance(payload, dict):
				continue
			if job_key is not None and payload.get("job_key") != job_key:
				continue
			records.append(cast("dict[str, Any]", payload))
		return records

	def latest_by_candidate(self, *, job_key: str) -> dict[str, dict[str, Any]]:
		latest: dict[str, dict[str, Any]] = {}
		for record in self.list_evaluations(job_key=job_key):
			key = str(record.get("candidate_key") or record.get("id"))
			current = latest.get(key)
			if current is None or str(record.get("created_at", "")) > str(current.get("created_at", "")):
				latest[key] = record
		return latest

	def find_unchanged(
		self,
		*,
		job_key: str,
		resume: dict[str, Any],
		source: dict[str, Any] | None,
		rubric: dict[str, Any],
	) -> dict[str, Any] | None:
		key = candidate_key(resume, source)
		record = self.latest_by_candidate(job_key=job_key).get(key)
		if record is None:
			return None
		if record.get("resume_fingerprint") != resume_fingerprint(resume):
			return None
		if record.get("rubric_fingerprint") != rubric_fingerprint(rubric):
			return None
		return record

	def rank(self, *, job_key: str, top: int) -> list[dict[str, Any]]:
		def sort_key(record: dict[str, Any]) -> tuple[float, float, str]:
			evaluation = record.get("evaluation")
			if not isinstance(evaluation, dict):
				return (-1.0, -1.0, "")
			return (
				_finite_sort_value(evaluation.get("total_score")),
				_finite_sort_value(evaluation.get("confidence")),
				str(record.get("created_at", "")),
			)
		limit = max(0, min(int(top), 10000))
		records = sorted(self.latest_by_candidate(job_key=job_key).values(), key=sort_key, reverse=True)
		return records[:limit]

	def set_status(self, record_id: str, status: str, *, note: str = "") -> dict[str, Any]:
		if status not in CANDIDATE_STATUSES:
			raise RecruiterAIError(f"不支持的候选人状态: {status}")
		record_id = _safe_storage_key(record_id, label="评估记录 ID")
		record = self.get_evaluation(record_id)
		record["status"] = status
		record["status_note"] = str(note)[:5000]
		record["updated_at"] = _utc_now()
		self._write(self.evaluations_dir / f"{record_id}.json", record)
		return record

	def save_reply(
		self,
		*,
		evaluation_id: str,
		intent: str,
		conversation: str,
		draft: dict[str, Any],
	) -> dict[str, Any]:
		# Replies must belong to a real evaluation so deletion and audit lifecycles cannot leave orphans.
		evaluation_id = _safe_storage_key(evaluation_id, label="评估记录 ID")
		evaluation_record = self.get_evaluation(evaluation_id)
		identity = str(evaluation_record.get("candidate_name") or "").strip()
		safe_conversation = redact_contact_text(conversation)
		if len(identity) >= 2:
			safe_conversation = safe_conversation.replace(identity, "[姓名已脱敏]")
		record_id = self._new_id("reply")
		record = {
			"schema_version": SCHEMA_VERSION,
			"id": record_id,
			"created_at": _utc_now(),
			"evaluation_id": evaluation_id,
			"intent": intent,
			"conversation": safe_conversation,
			"draft": draft,
			"sent": False,
			"requires_human_review": True,
		}
		self._write(self.replies_dir / f"{record_id}.json", record)
		return record

	def report(self, *, job_key: str, top: int = 10) -> dict[str, Any]:
		records = list(self.latest_by_candidate(job_key=job_key).values())
		buckets = {name: 0 for name in RECOMMENDATIONS}
		statuses = {name: 0 for name in CANDIDATE_STATUSES}
		for record in records:
			evaluation = record.get("evaluation")
			if isinstance(evaluation, dict) and evaluation.get("recommendation") in buckets:
				buckets[str(evaluation["recommendation"])] += 1
			status = str(record.get("status", "new"))
			if status in statuses:
				statuses[status] += 1
		return {
			"job_key": job_key,
			"total_candidates": len(records),
			"recommendation_counts": buckets,
			"status_counts": statuses,
			"top_candidates": summarize_ranking(self.rank(job_key=job_key, top=top)),
			"human_review_required": True,
		}


def summarize_ranking(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
	items: list[dict[str, Any]] = []
	for index, record in enumerate(records, 1):
		evaluation = record.get("evaluation")
		if not isinstance(evaluation, dict):
			continue
		items.append({
			"rank": index,
			"evaluation_id": record.get("id", ""),
			"candidate_key": record.get("candidate_key", ""),
			"candidate_name": record.get("candidate_name", ""),
			"total_score": evaluation.get("total_score"),
			"recommendation": evaluation.get("recommendation"),
			"confidence": evaluation.get("confidence"),
			"status": record.get("status", "new"),
			"strengths": evaluation.get("strengths", []),
			"concerns": evaluation.get("concerns", []),
			"next_questions": evaluation.get("next_questions", []),
			"summary": evaluation.get("summary", ""),
			"source": record.get("source", {}),
		})
	return items
