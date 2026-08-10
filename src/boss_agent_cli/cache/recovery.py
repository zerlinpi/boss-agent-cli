"""Fail-safe recovery for the rebuildable CLI cache database."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

_CORRUPTION_MARKERS = (
	"database disk image is malformed",
	"file is not a database",
	"not a database",
	"file is encrypted",
	"malformed database schema",
)


def _is_corruption_error(exc: sqlite3.DatabaseError) -> bool:
	message = str(exc).casefold()
	return any(marker in message for marker in _CORRUPTION_MARKERS)


def _quarantine_database(db_path: Path) -> None:
	"""Move a corrupt cache database and sidecars aside for diagnosis instead of deleting them."""
	suffix = f".corrupt-{uuid4().hex[:12]}"
	for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
		if not path.exists():
			continue
		destination = path.with_name(f"{path.name}{suffix}")
		path.replace(destination)


def install_cache_recovery(store_cls: type[Any]) -> None:
	"""Recreate only clearly corrupt cache DBs; operational/locking errors still surface."""
	if getattr(store_cls, "_boss_cache_recovery_installed", False):
		return
	original_init: Callable[..., None] = store_cls.__init__

	def __init__(self: Any, db_path: Path, **kwargs: Any) -> None:
		try:
			original_init(self, db_path, **kwargs)
			return
		except sqlite3.DatabaseError as exc:
			if not _is_corruption_error(exc):
				raise
			connection = getattr(self, "_conn", None)
			if connection is not None:
				try:
					connection.close()
				except sqlite3.Error:
					pass
			try:
				_quarantine_database(Path(db_path))
			except OSError as quarantine_error:
				raise RuntimeError(
					f"缓存数据库损坏且无法隔离: {db_path}: {quarantine_error}"
				) from exc
		original_init(self, db_path, **kwargs)

	setattr(store_cls, "__init__", __init__)
	setattr(store_cls, "_boss_cache_recovery_installed", True)
