"""Append-only audit trail for recruiter Web actions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4


def _now() -> str:
	return datetime.now(timezone.utc).isoformat()


def _restrict_permissions(path: Path, mode: int) -> None:
	try:
		path.chmod(mode)
	except OSError:
		pass


class AuditLog:
	"""Persist compact, non-secret operation records as JSON Lines."""

	def __init__(self, data_dir: Path):
		self.path = data_dir / "recruiter-ai" / "audit.jsonl"
		self.path.parent.mkdir(parents=True, exist_ok=True)
		_restrict_permissions(self.path.parent, 0o700)
		if self.path.exists():
			_restrict_permissions(self.path, 0o600)
		self._lock = Lock()

	def append(
		self,
		action: str,
		*,
		entity_type: str,
		entity_id: str = "",
		summary: str,
		metadata: dict[str, Any] | None = None,
	) -> dict[str, Any]:
		record = {
			"id": f"audit_{uuid4().hex[:12]}",
			"created_at": _now(),
			"action": action,
			"entity_type": entity_type,
			"entity_id": entity_id,
			"summary": summary,
			"metadata": metadata or {},
		}
		line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
		with self._lock:
			if self.path.is_file() and self.path.stat().st_size > 5 * 1024 * 1024:
				lines = self.path.read_text(encoding="utf-8").splitlines()[-2000:]
				self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
				_restrict_permissions(self.path, 0o600)
			with self.path.open("a", encoding="utf-8") as handle:
				handle.write(line)
			_restrict_permissions(self.path, 0o600)
		return record

	def list(self, *, limit: int = 100, action: str | None = None) -> list[dict[str, Any]]:
		if not self.path.is_file():
			return []
		with self._lock:
			lines = self.path.read_text(encoding="utf-8").splitlines()
		items: list[dict[str, Any]] = []
		for line in reversed(lines):
			try:
				item = json.loads(line)
			except json.JSONDecodeError:
				continue
			if not isinstance(item, dict):
				continue
			if action and item.get("action") != action:
				continue
			items.append(item)
			if len(items) >= max(1, min(limit, 500)):
				break
		return items
