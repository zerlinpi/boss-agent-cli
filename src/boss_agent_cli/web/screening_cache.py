"""Per-request candidate index cache to avoid repeated evaluation-directory scans."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator

from boss_agent_cli.recruiter_candidate_state import canonical_candidate_key
from boss_agent_cli.web import controller as controller_module

_INSTALLED = False
_SCREEN_CACHE: ContextVar[dict[tuple[int, str], dict[str, dict[str, Any]]] | None] = ContextVar(
	"boss_recruiter_screen_cache",
	default=None,
)


@contextmanager
def screening_cache_scope(store: Any, job_key: str) -> Iterator[None]:
	"""Build one latest-candidate index for a request/screening scope and release it afterwards."""
	key = (id(store), job_key)
	loader = getattr(store.__class__, "_boss_uncached_latest_by_candidate")
	scope = _SCREEN_CACHE.get()
	if scope is not None:
		# Nested operations may legitimately ask for another job/store. Add that snapshot lazily
		# instead of silently falling back to repeated disk scans.
		if key not in scope:
			scope[key] = loader(store, job_key=job_key)
		yield
		return
	cache = {key: loader(store, job_key=job_key)}
	token = _SCREEN_CACHE.set(cache)
	try:
		yield
	finally:
		_SCREEN_CACHE.reset(token)


def install_screening_cache() -> None:
	"""Cache latest candidate records during screening and composite read requests."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	store_cls = controller_module.RecruiterAIStore
	original_latest: Callable[..., dict[str, dict[str, Any]]] = store_cls.latest_by_candidate
	original_save: Callable[..., dict[str, Any]] = store_cls.save_evaluation
	original_screen_local: Callable[..., dict[str, Any]] = controller_cls.screen_local
	original_screen_boss: Callable[..., dict[str, Any]] = controller_cls.screen_boss
	original_candidates: Callable[..., dict[str, Any]] = controller_cls.candidates
	original_report: Callable[..., dict[str, Any]] = controller_cls.report
	original_analytics: Callable[..., dict[str, Any]] = controller_cls.analytics
	setattr(store_cls, "_boss_uncached_latest_by_candidate", original_latest)

	def latest_by_candidate(self: Any, *, job_key: str) -> dict[str, dict[str, Any]]:
		scope = _SCREEN_CACHE.get()
		if scope is not None:
			cached = scope.get((id(self), job_key))
			if cached is not None:
				return cached
		return original_latest(self, job_key=job_key)

	def save_evaluation(self: Any, **kwargs: Any) -> dict[str, Any]:
		record = original_save(self, **kwargs)
		job_key = str(record.get("job_key") or kwargs.get("job_key") or "")
		scope = _SCREEN_CACHE.get()
		if scope is not None and job_key:
			cached = scope.get((id(self), job_key))
			if cached is not None:
				cached[canonical_candidate_key(record)] = record
		return record

	def screen_local(self: Any, payload: dict[str, Any], *, progress: Any = None) -> dict[str, Any]:
		job_key = str(payload.get("job_key") or "").strip()
		if not job_key:
			return original_screen_local(self, payload, progress=progress)
		with screening_cache_scope(self.store, job_key):
			return original_screen_local(self, payload, progress=progress)

	def screen_boss(self: Any, payload: dict[str, Any], *, progress: Any = None) -> dict[str, Any]:
		job_key = str(payload.get("job_key") or "").strip()
		if not job_key:
			return original_screen_boss(self, payload, progress=progress)
		with screening_cache_scope(self.store, job_key):
			return original_screen_boss(self, payload, progress=progress)

	def candidates(self: Any, job_key: str, *, top: int = 200) -> dict[str, Any]:
		if not job_key:
			return original_candidates(self, job_key, top=top)
		with screening_cache_scope(self.store, job_key):
			return original_candidates(self, job_key, top=top)

	def report(self: Any, job_key: str, *, top: int = 10) -> dict[str, Any]:
		if not job_key:
			return original_report(self, job_key, top=top)
		with screening_cache_scope(self.store, job_key):
			return original_report(self, job_key, top=top)

	def analytics(self: Any, job_key: str) -> dict[str, Any]:
		if not job_key:
			return original_analytics(self, job_key)
		with screening_cache_scope(self.store, job_key):
			return original_analytics(self, job_key)

	setattr(store_cls, "latest_by_candidate", latest_by_candidate)
	setattr(store_cls, "save_evaluation", save_evaluation)
	setattr(controller_cls, "screen_local", screen_local)
	setattr(controller_cls, "screen_boss", screen_boss)
	setattr(controller_cls, "candidates", candidates)
	setattr(controller_cls, "report", report)
	setattr(controller_cls, "analytics", analytics)
