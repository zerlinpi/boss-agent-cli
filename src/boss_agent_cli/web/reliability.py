"""Reliability guards for the recruiter Web workspace.

This module keeps compatibility fixes small and isolated from the large Web
controller. It is installed once by :mod:`boss_agent_cli.web`.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from boss_agent_cli.web import controller as controller_module

_INSTALLED = False


class _LazyAIService:
	"""Resolve the configured AI service only when the first model call is made."""

	def __init__(self, controller: Any, resolver: Callable[[Any], Any]):
		self._controller = controller
		self._resolver = resolver
		self._resolved: Any | None = None

	def _service(self) -> Any:
		if self._resolved is None:
			self._resolved = self._resolver(self._controller)
		return self._resolved

	def chat(self, *args: Any, **kwargs: Any) -> str:
		return str(self._service().chat(*args, **kwargs))


def _as_utc(value: Any) -> datetime | None:
	"""Parse current and legacy timestamps into an aware UTC datetime."""
	try:
		parsed = datetime.fromisoformat(str(value or ""))
	except (TypeError, ValueError):
		return None
	if parsed.tzinfo is None:
		return parsed.replace(tzinfo=timezone.utc)
	return parsed.astimezone(timezone.utc)


def _normalize_friend_id(value: Any) -> int | None:
	"""Return the integer friend id required by chat_history, or None when malformed."""
	if isinstance(value, bool) or value in (None, ""):
		return None
	try:
		parsed = int(str(value).strip())
	except (TypeError, ValueError):
		return None
	return parsed if parsed > 0 else None


def install_controller_reliability() -> None:
	"""Install lazy AI resolution, stable refs, bounded reads, and legacy-safe analytics."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	original_service = controller_cls._service
	original_extract_candidate_ref = controller_module.extract_candidate_ref

	def lazy_service(self: Any) -> _LazyAIService:
		return _LazyAIService(self, original_service)

	def extract_candidate_ref(item: dict[str, Any], *, default_job_id: str | None = None) -> dict[str, Any]:
		ref = original_extract_candidate_ref(item, default_job_id=default_job_id)
		ref["friend_id"] = _normalize_friend_id(ref.get("friend_id"))
		return ref

	def analytics(self: Any, job_key: str) -> dict[str, Any]:
		records = list(self.store.latest_by_candidate(job_key=job_key).values())
		scores: list[float] = []
		confidences: list[float] = []
		recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
		recent = 0
		for record in records:
			evaluation = record.get("evaluation")
			if isinstance(evaluation, dict):
				score = evaluation.get("total_score")
				confidence = evaluation.get("confidence")
				if isinstance(score, (int, float)) and not isinstance(score, bool):
					scores.append(float(score))
				if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
					confidences.append(float(confidence))
			created = _as_utc(record.get("created_at"))
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
		status_counts = report.get("status_counts", {})
		total = len(records)
		interviewed = int(status_counts.get("interview", 0)) + int(status_counts.get("hired", 0))
		return {
			"total": total,
			"average_score": round(statistics.mean(scores), 1) if scores else 0,
			"median_score": round(statistics.median(scores), 1) if scores else 0,
			"average_confidence": round(statistics.mean(confidences), 3) if confidences else 0,
			"recent_7d": recent,
			"interview_conversion": round(interviewed / total * 100, 1) if total else 0,
			"score_distribution": distribution,
		}

	def replies(self: Any, *, evaluation_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
		# Keep the API contract bounded even when a caller bypasses the browser UI.
		bounded_limit = max(1, min(int(limit), 500))
		items: list[dict[str, Any]] = []
		for path in sorted(self.store.replies_dir.glob("reply_*.json"), reverse=True):
			try:
				payload = json.loads(path.read_text(encoding="utf-8"))
			except (OSError, json.JSONDecodeError):
				continue
			if not isinstance(payload, dict):
				continue
			if evaluation_id and payload.get("evaluation_id") != evaluation_id:
				continue
			items.append(payload)
			if len(items) >= bounded_limit:
				break
		return items

	setattr(controller_cls, "_service", lazy_service)
	setattr(controller_cls, "analytics", analytics)
	setattr(controller_cls, "replies", replies)
	setattr(controller_module, "extract_candidate_ref", extract_candidate_ref)


def install_server_reliability(server_module: Any) -> None:
	"""Validate explicit native Web ports before attempting to bind sockets."""
	original_build_server = server_module.build_server
	if getattr(original_build_server, "_boss_reliability_wrapped", False):
		return

	def build_server(controller: Any, *, host: str = "127.0.0.1", port: int = 8765) -> Any:
		if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
			raise ValueError("Web 控制台端口必须是 0-65535 的整数（0 仅用于测试时自动分配）")
		return original_build_server(controller, host=host, port=port)

	setattr(build_server, "_boss_reliability_wrapped", True)
	setattr(server_module, "build_server", build_server)
