"""Per-screening candidate index cache to avoid repeated evaluation-directory scans."""

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
	"""Build one latest-candidate index for a screening run and release it afterwards."""
	scope = _SCREEN_CACHE.get()
	if scope is not None:
		yield
		return
	key = (id(store), job_key)
	# Call the class method currently installed before this module wraps it. The installer stores
	# that implementation on the class so tests and nested screen wrappers share one snapshot.
	loader = getattr(store.__class__, "_boss_uncached_latest_by_candidate")
	cache = {key: loader(store, job_key=job_key)}
	token = _SCREEN_CACHE.set(cache)
	try:
		yield
	finally:
		_SCREEN_CACHE.reset(token)


def install_screening_cache() -> None:
	"""Cache latest candidate records only while local/BOSS screening is running."""
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

	setattr(store_cls, "latest_by_candidate", latest_by_candidate)
	setattr(store_cls, "save_evaluation", save_evaluation)
	setattr(controller_cls, "screen_local", screen_local)
	setattr(controller_cls, "screen_boss", screen_boss)
