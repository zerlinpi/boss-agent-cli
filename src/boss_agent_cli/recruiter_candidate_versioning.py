"""Legacy-safe candidate version ordering for recruiter evaluation history."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from boss_agent_cli.recruiter_candidate_state import canonical_candidate_key

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


def install_candidate_version_ordering(store_cls: type[Any]) -> None:
	"""Select and rank candidate versions by actual UTC time, not ISO string ordering."""
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
		return sorted(self.latest_by_candidate(job_key=job_key).values(), key=sort_key, reverse=True)[:limit]

	setattr(store_cls, "latest_by_candidate", latest_by_candidate)
	setattr(store_cls, "rank", rank)
