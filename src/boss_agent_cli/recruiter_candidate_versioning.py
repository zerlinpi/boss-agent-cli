"""Legacy-safe candidate version ordering for recruiter evaluation history."""

from __future__ import annotations

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


def install_candidate_version_ordering(store_cls: type[Any]) -> None:
	"""Select latest logical candidate versions by actual UTC time, not ISO string ordering."""
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

	setattr(store_cls, "latest_by_candidate", latest_by_candidate)
