"""Cross-process lease shared by CLI, Web, and scheduled recruiter autopilot runs."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

import click


class RecruiterAutopilotBusy(RuntimeError):
	"""Raised when another process already owns the recruiter autopilot lease."""

	code = "AUTOPILOT_ALREADY_RUNNING"


def _lock_windows(fd: int) -> Callable[[], None]:
	import msvcrt

	if os.fstat(fd).st_size < 1:
		os.ftruncate(fd, 1)
	os.lseek(fd, 0, os.SEEK_SET)
	try:
		msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
	except OSError as exc:
		raise RecruiterAutopilotBusy("已有 Recruiter Autopilot 正在运行，本轮不会重复执行") from exc

	def unlock() -> None:
		os.lseek(fd, 0, os.SEEK_SET)
		msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

	return unlock


def _lock_posix(fd: int) -> Callable[[], None]:
	import fcntl

	try:
		fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
	except OSError as exc:
		raise RecruiterAutopilotBusy("已有 Recruiter Autopilot 正在运行，本轮不会重复执行") from exc

	def unlock() -> None:
		fcntl.flock(fd, fcntl.LOCK_UN)

	return unlock


@contextmanager
def recruiter_autopilot_lease(data_dir: Path) -> Iterator[None]:
	"""Hold an OS-managed lock; process exit automatically releases the lease."""
	root = data_dir / "recruiter-ai"
	root.mkdir(parents=True, exist_ok=True)
	path = root / ".autopilot.lock"
	fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
	unlock: Callable[[], None] | None = None
	try:
		unlock = _lock_windows(fd) if os.name == "nt" else _lock_posix(fd)
		try:
			path.chmod(0o600)
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


def install_autopilot_command_lease(command: click.Command) -> None:
	"""Wrap the Click callback so manual CLI runs share the same lease as Web/scheduler runs."""
	if getattr(command, "_boss_autopilot_lease_installed", False):
		return
	original = command.callback
	if original is None:
		return

	def callback(*args: Any, **kwargs: Any) -> Any:
		ctx = click.get_current_context()
		data_dir = Path(ctx.obj["data_dir"])
		try:
			with recruiter_autopilot_lease(data_dir):
				return original(*args, **kwargs)
		except RecruiterAutopilotBusy as exc:
			from boss_agent_cli.display import handle_error_output

			handle_error_output(
				ctx,
				"recruiter-ai-autopilot",
				code=exc.code,
				message=str(exc),
				recoverable=True,
				recovery_action="等待当前 Autopilot 完成，或在 Web 的任务页面取消正在运行的任务",
			)
			return None

	command.callback = callback
	setattr(command, "_boss_autopilot_lease_installed", True)
