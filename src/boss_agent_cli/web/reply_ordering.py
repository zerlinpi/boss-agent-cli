"""Stable chronological ordering for recruiter reply history."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from heapq import nlargest
from typing import Any

from boss_agent_cli.recruiter_ai import RecruiterAIError
from boss_agent_cli.web import controller as controller_module

_INSTALLED = False


def _timestamp(value: Any) -> float:
	text = str(value or "").strip()
	if not text:
		return float("-inf")
	if text.endswith("Z"):
		text = text[:-1] + "+00:00"
	try:
		parsed = datetime.fromisoformat(text)
	except ValueError:
		return float("-inf")
	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=timezone.utc)
	return parsed.astimezone(timezone.utc).timestamp()


def _reply_key(record: dict[str, Any]) -> tuple[float, str]:
	return (_timestamp(record.get("created_at")), str(record.get("id") or ""))


def install_reply_ordering() -> None:
	"""Read all matching reply files, fail on corruption, and retain only newest bounded results."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController

	def replies(self: Any, *, evaluation_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
		if isinstance(limit, bool) or not isinstance(limit, int):
			bounded_limit = 100
		else:
			bounded_limit = max(1, min(limit, 500))

		def records():
			for path in self.store.replies_dir.glob("reply_*.json"):
				try:
					payload = json.loads(path.read_text(encoding="utf-8"))
				except (OSError, json.JSONDecodeError) as exc:
					raise RecruiterAIError(f"回复记录损坏: {path.stem}") from exc
				if not isinstance(payload, dict):
					raise RecruiterAIError(f"回复记录损坏: {path.stem}")
				if evaluation_id and str(payload.get("evaluation_id") or "") != evaluation_id:
					continue
				yield payload

		return nlargest(bounded_limit, records(), key=_reply_key)

	setattr(controller_cls, "replies", replies)
