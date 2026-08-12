"""Cross-process single-runner lease for automation cycles."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from boss_agent_cli.automation.models import CycleResult


class AutomationRunnerBusy(RuntimeError):
	"""Raised when another process already owns the automation cycle lease."""


def _now() -> str:
	return datetime.now(timezone.utc).isoformat()


def _lock_windows(fd: int) -> Callable[[], None]:
	import msvcrt

	api: Any = msvcrt
	if os.fstat(fd).st_size < 1:
		os.ftruncate(fd, 1)
	os.lseek(fd, 0, os.SEEK_SET)
	try:
		api.locking(fd, api.LK_NBLCK, 1)
	except OSError as exc:
		raise AutomationRunnerBusy("已有 automation runner 正在执行，本轮不重复运行") from exc

	def unlock() -> None:
		os.lseek(fd, 0, os.SEEK_SET)
		api.locking(fd, api.LK_UNLCK, 1)

	return unlock


def _lock_posix(fd: int) -> Callable[[], None]:
	import fcntl

	try:
		fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
	except OSError as exc:
		raise AutomationRunnerBusy("已有 automation runner 正在执行，本轮不重复运行") from exc

	def unlock() -> None:
		fcntl.flock(fd, fcntl.LOCK_UN)

	return unlock


def _write_metadata(path: Path) -> None:
	"""Persist human-readable owner metadata separately from the mandatory Windows lock."""
	metadata = json.dumps(
		{"pid": os.getpid(), "started_at": _now()},
		ensure_ascii=False,
	).encode("utf-8")
	fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
	try:
		os.write(fd, metadata)
		os.fsync(fd)
	finally:
		os.close(fd)
	try:
		path.chmod(0o600)
	except OSError:
		pass


@contextmanager
def runner_lease(root: Path) -> Iterator[None]:
	"""Hold an OS-managed lock that is automatically released if the process exits.

	The lock itself lives in a private guard file. Owner metadata remains in
	``.runner.lock`` so diagnostics can read it even while Windows holds its mandatory
	byte-range lock; locking that same metadata file made reads fail with
	``PermissionError`` on Windows.
	"""
	root.mkdir(parents=True, exist_ok=True)
	metadata_path = root / ".runner.lock"
	guard_path = root / ".runner.lock.guard"
	fd = os.open(guard_path, os.O_RDWR | os.O_CREAT, 0o600)
	unlock: Callable[[], None] | None = None
	try:
		unlock = _lock_windows(fd) if os.name == "nt" else _lock_posix(fd)
		_write_metadata(metadata_path)
		try:
			guard_path.chmod(0o600)
		except OSError:
			pass
		yield
	finally:
		if unlock is not None:
			try:
				unlock()
			except OSError:
				pass
		os.close(fd)


def install_runner_lease(runner_cls: type[Any]) -> None:
	"""Wrap run_cycle so a second process becomes a controlled no-op instead of double-executing."""
	if getattr(runner_cls, "_boss_runner_lease_installed", False):
		return
	original_run_cycle: Callable[..., CycleResult] = runner_cls.run_cycle

	def run_cycle(self: Any, *args: Any, **kwargs: Any) -> CycleResult:
		try:
			with runner_lease(self.store.root):
				return original_run_cycle(self, *args, **kwargs)
		except AutomationRunnerBusy as exc:
			now = _now()
			return CycleResult(
				cycle_id=f"busy-{os.getpid()}",
				started_at=now,
				finished_at=now,
				duration_ms=0,
				references_scanned=0,
				pending_processed=0,
				events=[],
				errors=[str(exc)],
				stopped=False,
			)

	setattr(runner_cls, "run_cycle", run_cycle)
	setattr(runner_cls, "_boss_runner_lease_installed", True)
