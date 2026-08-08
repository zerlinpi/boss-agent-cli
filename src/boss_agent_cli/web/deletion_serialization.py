"""Serialize destructive recruiter actions against screening task submission."""

from __future__ import annotations

from typing import Any, Callable

from boss_agent_cli.web import lifecycle as lifecycle_module

_INSTALLED = False


def install_deletion_serialization(server_module: Any) -> None:
	"""Close the check-then-delete race with concurrent screening submissions."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	application_cls = server_module.RecruiterWebApplication
	original_post: Callable[..., Any] = application_cls.post

	def post(self: Any, path: str, payload: dict[str, Any]) -> Any:
		is_job_delete = path == "/api/jobs" and bool(payload.get("_delete"))
		is_candidate_delete = (
			path.startswith("/api/candidates/")
			and path.endswith("/status")
			and payload.get("status") == "__delete__"
		)
		if not (is_job_delete or is_candidate_delete):
			return original_post(self, path, payload)

		# lifecycle.install_server_extensions() uses this same lock around the active-screening
		# check plus task submission. Holding it across deletion makes the inverse operation atomic:
		# no new screening can be submitted after the deletion check but before data removal finishes.
		with lifecycle_module._SCREEN_SUBMIT_LOCK:
			return original_post(self, path, payload)

	setattr(application_cls, "post", post)
