"""Limit automatic BOSS reply drafts to evaluations created by the current screening run."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Callable

from boss_agent_cli.web import controller as controller_module
from boss_agent_cli.web.screening_cache import screening_cache_scope

_INSTALLED = False
_DRAFT_SCOPE: ContextVar[dict[str, Any] | None] = ContextVar("boss_recruiter_draft_scope", default=None)


def install_boss_draft_scope() -> None:
	"""Keep historical candidates in ranking while excluding them from automatic draft generation."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	store_cls = controller_module.RecruiterAIStore
	original_screen_boss: Callable[..., dict[str, Any]] = controller_cls.screen_boss
	original_rank: Callable[..., list[dict[str, Any]]] = store_cls.rank

	def rank(self: Any, *, job_key: str, top: int) -> list[dict[str, Any]]:
		scope = _DRAFT_SCOPE.get()
		if not scope or scope.get("job_key") != job_key:
			return original_rank(self, job_key=job_key, top=top)
		scope["rank_calls"] = int(scope.get("rank_calls", 0)) + 1
		if scope["rank_calls"] != 1 or int(scope.get("draft_top", 0)) <= 0:
			return original_rank(self, job_key=job_key, top=top)

		existing_ids = scope.get("existing_ids")
		if not isinstance(existing_ids, set):
			return original_rank(self, job_key=job_key, top=top)
		# The original store caps top at 10k. Pull enough ranked records so a highly ranked historical
		# candidate cannot hide a newly evaluated candidate before the draft-only filter is applied.
		records = original_rank(self, job_key=job_key, top=10_000)
		new_records = [record for record in records if str(record.get("id") or "") not in existing_ids]
		return new_records[: max(0, int(top))]

	def screen_boss(self: Any, payload: dict[str, Any], *, progress: Any = None) -> dict[str, Any]:
		job_key = str(payload.get("job_key") or "").strip()
		if not job_key:
			return original_screen_boss(self, payload, progress=progress)
		with screening_cache_scope(self.store, job_key):
			existing_ids = {
				str(record.get("id") or "")
				for record in self.store.latest_by_candidate(job_key=job_key).values()
				if record.get("id")
			}
			token = _DRAFT_SCOPE.set({
				"job_key": job_key,
				"existing_ids": existing_ids,
				"draft_top": payload.get("draft_top", 0),
				"rank_calls": 0,
			})
			try:
				return original_screen_boss(self, payload, progress=progress)
			finally:
				_DRAFT_SCOPE.reset(token)

	setattr(store_cls, "rank", rank)
	setattr(controller_cls, "screen_boss", screen_boss)
