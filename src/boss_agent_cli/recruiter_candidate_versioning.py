"""Legacy-safe candidate version ordering for recruiter evaluation history."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import boss_agent_cli.recruiter_ai_store as store_module
from boss_agent_cli.recruiter_ai_models import CANDIDATE_STATUSES, RECOMMENDATIONS
from boss_agent_cli.recruiter_candidate_state import canonical_candidate_key
from boss_agent_cli.recruiter_evaluation_freshness import get_saved_job_optional

_MIN_UTC = datetime.min.replace(tzinfo=timezone.utc)
_INSTALLED = False


def _created_at_utc(record: dict[str, Any]) -> datetime:
	text = str(record.get("created_at") or "").strip()
	if not text:
		return _MIN_UTC
	if text.endswith("Z"):
		text = text[:-1] + "+00:00"
	try:
		parsed = datetime.fromisoformat(text)
	except (TypeError, ValueError):
		return _MIN_UTC
	if parsed.tzinfo is None:
		return parsed.replace(tzinfo=timezone.utc)
	return parsed.astimezone(timezone.utc)


def _version_key(record: dict[str, Any]) -> tuple[datetime, str]:
	return _created_at_utc(record), str(record.get("id") or "")


def _finite_score(value: Any) -> float:
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		return -1.0
	number = float(value)
	return number if math.isfinite(number) else -1.0


def _split_current_job_records(self: Any, job_key: str) -> tuple[list[dict[str, Any]], int]:
	all_records = list(self.latest_by_candidate(job_key=job_key).values())
	job = get_saved_job_optional(self, job_key)
	if job is None:
		# Ad-hoc CLI evaluations can intentionally exist without a persisted job profile.
		return all_records, 0
	jd_text = str(job.get("jd_text") or "")
	rubric_fingerprint = str(job.get("rubric_fingerprint") or "")
	current = [
		record for record in all_records
		if str(record.get("jd_text") or "") == jd_text
		and str(record.get("rubric_fingerprint") or "") == rubric_fingerprint
	]
	return current, len(all_records) - len(current)


def _current_job_records(self: Any, job_key: str) -> list[dict[str, Any]]:
	return _split_current_job_records(self, job_key)[0]


def install_candidate_version_ordering(store_cls: type[Any]) -> None:
	"""Select latest versions by UTC and keep current rankings on the saved job configuration."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	def latest_by_candidate(self: Any, *, job_key: str) -> dict[str, dict[str, Any]]:
		latest: dict[str, dict[str, Any]] = {}
		for record in self.list_evaluations(job_key=job_key):
			key = canonical_candidate_key(record)
			current = latest.get(key)
			if current is None or _version_key(record) > _version_key(current):
				latest[key] = record
		return latest

	def rank(self: Any, *, job_key: str, top: int) -> list[dict[str, Any]]:
		def sort_key(record: dict[str, Any]) -> tuple[float, float, datetime, str]:
			evaluation = record.get("evaluation")
			if not isinstance(evaluation, dict):
				return -1.0, -1.0, _MIN_UTC, str(record.get("id") or "")
			created_at, record_id = _version_key(record)
			return (
				_finite_score(evaluation.get("total_score")),
				_finite_score(evaluation.get("confidence")),
				created_at,
				record_id,
			)

		limit = max(0, min(int(top), 10_000))
		return sorted(_current_job_records(self, job_key), key=sort_key, reverse=True)[:limit]

	def report(self: Any, *, job_key: str, top: int = 10) -> dict[str, Any]:
		records, stale_count = _split_current_job_records(self, job_key)
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
			"stale_count": stale_count,
			"recommendation_counts": buckets,
			"status_counts": statuses,
			"top_candidates": store_module.summarize_ranking(self.rank(job_key=job_key, top=top)),
			"human_review_required": True,
		}

	setattr(store_cls, "latest_by_candidate", latest_by_candidate)
	setattr(store_cls, "rank", rank)
	setattr(store_cls, "report", report)
