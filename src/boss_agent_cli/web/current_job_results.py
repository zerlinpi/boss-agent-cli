"""Keep Web ranking and analytics scoped to evaluations for the current saved job configuration."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from importlib.resources import files
from typing import Any, Callable, Iterator

from boss_agent_cli.web import controller as controller_module

_INSTALLED = False
_ASSETS_INSTALLED = False
_SCOPE: ContextVar[dict[str, Any] | None] = ContextVar("boss_recruiter_current_job_results", default=None)


def _matches_current_job(record: dict[str, Any], scope: dict[str, Any]) -> bool:
	return (
		str(record.get("jd_text") or "") == scope["jd_text"]
		and str(record.get("rubric_fingerprint") or "") == scope["rubric_fingerprint"]
	)


@contextmanager
def _current_job_scope(controller: Any, job_key: str) -> Iterator[dict[str, Any] | None]:
	existing = _SCOPE.get()
	if existing is not None and existing.get("store_id") == id(controller.store) and existing.get("job_key") == job_key:
		yield existing
		return
	try:
		job = controller.store.get_job(job_key)
	except Exception:
		yield None
		return
	scope = {
		"store_id": id(controller.store),
		"job_key": job_key,
		"jd_text": str(job.get("jd_text") or ""),
		"rubric_fingerprint": str(job.get("rubric_fingerprint") or ""),
		"stale_count": 0,
		"all_count": 0,
	}
	token = _SCOPE.set(scope)
	try:
		yield scope
	finally:
		_SCOPE.reset(token)


def _attach_stale_count(payload: dict[str, Any], scope: dict[str, Any] | None) -> dict[str, Any]:
	if scope is None:
		return payload
	stale_count = int(scope.get("stale_count", 0))
	payload["stale_count"] = stale_count
	for key in ("report", "analytics"):
		child = payload.get(key)
		if isinstance(child, dict):
			child["stale_count"] = stale_count
	return payload


def install_current_job_results() -> None:
	"""Exclude evaluations produced for older JD/rubric versions from current Web decisions."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	store_cls = controller_module.RecruiterAIStore
	original_latest: Callable[..., dict[str, dict[str, Any]]] = store_cls.latest_by_candidate
	original_candidates: Callable[..., dict[str, Any]] = controller_cls.candidates
	original_report: Callable[..., dict[str, Any]] = controller_cls.report
	original_analytics: Callable[..., dict[str, Any]] = controller_cls.analytics
	original_export: Callable[..., dict[str, str]] = controller_cls.export_candidates

	def latest_by_candidate(self: Any, *, job_key: str) -> dict[str, dict[str, Any]]:
		records = original_latest(self, job_key=job_key)
		scope = _SCOPE.get()
		if scope is None or scope.get("store_id") != id(self) or scope.get("job_key") != job_key:
			return records
		filtered = {key: record for key, record in records.items() if _matches_current_job(record, scope)}
		scope["all_count"] = len(records)
		scope["stale_count"] = len(records) - len(filtered)
		return filtered

	def candidates(self: Any, job_key: str, *, top: int = 200) -> dict[str, Any]:
		with _current_job_scope(self, job_key) as scope:
			return _attach_stale_count(original_candidates(self, job_key, top=top), scope)

	def report(self: Any, job_key: str, *, top: int = 10) -> dict[str, Any]:
		with _current_job_scope(self, job_key) as scope:
			result = original_report(self, job_key, top=top)
			if scope is not None:
				result["stale_count"] = int(scope.get("stale_count", 0))
			return result

	def analytics(self: Any, job_key: str) -> dict[str, Any]:
		with _current_job_scope(self, job_key) as scope:
			result = original_analytics(self, job_key)
			if scope is not None:
				result["stale_count"] = int(scope.get("stale_count", 0))
			return result

	def export_candidates(self: Any, job_key: str) -> dict[str, str]:
		with _current_job_scope(self, job_key):
			return original_export(self, job_key)

	setattr(store_cls, "latest_by_candidate", latest_by_candidate)
	setattr(controller_cls, "candidates", candidates)
	setattr(controller_cls, "report", report)
	setattr(controller_cls, "analytics", analytics)
	setattr(controller_cls, "export_candidates", export_candidates)


def install_current_job_result_assets(server_module: Any) -> None:
	"""Append a small UI warning for candidates whose scores require re-screening."""
	global _ASSETS_INSTALLED
	if _ASSETS_INSTALLED:
		return
	_ASSETS_INSTALLED = True
	application_cls = server_module.RecruiterWebApplication
	original_asset: Callable[..., tuple[bytes, str]] = application_cls.asset

	def asset(self: Any, name: str) -> tuple[bytes, str]:
		content, content_type = original_asset(self, name)
		if name == "app.js":
			content += b"\n" + files("boss_agent_cli.web.assets").joinpath("stale_results.js").read_bytes()
		elif name == "styles.css":
			content += b"\n" + files("boss_agent_cli.web.assets").joinpath("stale_results.css").read_bytes()
		return content, content_type

	setattr(application_cls, "asset", asset)
