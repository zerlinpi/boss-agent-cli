"""Defensive analytics calculations for persisted recruiter evaluations."""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

_INSTALLED = False


def _finite_number(value: Any) -> float | None:
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		return None
	number = float(value)
	return number if math.isfinite(number) else None


def _utc_datetime(value: Any) -> datetime | None:
	if not isinstance(value, str) or not value.strip():
		return None
	text = value.strip()
	if text.endswith("Z"):
		text = f"{text[:-1]}+00:00"
	try:
		parsed = datetime.fromisoformat(text)
	except (ValueError, OverflowError):
		return None
	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=timezone.utc)
	try:
		return parsed.astimezone(timezone.utc)
	except (ValueError, OverflowError):
		return None


def _count(value: Any) -> int:
	try:
		result = int(value)
	except (TypeError, ValueError, OverflowError):
		return 0
	return max(0, result)


def install_analytics_safety(controller_module: Any) -> None:
	"""Replace analytics with timezone-safe, finite-number-only calculations."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True
	controller_cls = controller_module.RecruiterWebController

	def analytics(self: Any, job_key: str) -> dict[str, Any]:
		records = list(self.store.latest_by_candidate(job_key=job_key).values())
		scores: list[float] = []
		confidences: list[float] = []
		recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
		recent = 0
		for record in records:
			evaluation = record.get("evaluation")
			if isinstance(evaluation, dict):
				score = _finite_number(evaluation.get("total_score"))
				confidence = _finite_number(evaluation.get("confidence"))
				if score is not None:
					scores.append(score)
				if confidence is not None:
					confidences.append(confidence)
			created = _utc_datetime(record.get("created_at"))
			if created is not None and created >= recent_cutoff:
				recent += 1

		distribution = {"0-49": 0, "50-69": 0, "70-84": 0, "85-100": 0}
		for score in scores:
			if score < 50:
				distribution["0-49"] += 1
			elif score < 70:
				distribution["50-69"] += 1
			elif score < 85:
				distribution["70-84"] += 1
			else:
				distribution["85-100"] += 1

		report = self.store.report(job_key=job_key, top=10)
		status_counts = report.get("status_counts")
		if not isinstance(status_counts, dict):
			status_counts = {}
		total = len(records)
		interviewed = _count(status_counts.get("interview")) + _count(status_counts.get("hired"))
		return {
			"total": total,
			"average_score": round(statistics.mean(scores), 1) if scores else 0,
			"median_score": round(statistics.median(scores), 1) if scores else 0,
			"average_confidence": round(statistics.mean(confidences), 3) if confidences else 0,
			"recent_7d": recent,
			"interview_conversion": round(interviewed / total * 100, 1) if total else 0,
			"score_distribution": distribution,
		}

	setattr(controller_cls, "analytics", analytics)
