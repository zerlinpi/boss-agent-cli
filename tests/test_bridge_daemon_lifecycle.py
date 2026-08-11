import signal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from boss_agent_cli.bridge import daemon


def _paths(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
	pid_path = tmp_path / "bridge" / "daemon.pid"
	log_path = tmp_path / "bridge" / "daemon.log"
	monkeypatch.setattr(daemon, "_PID_FILE", pid_path)
	monkeypatch.setattr(daemon, "_LOG_FILE", log_path)
	return pid_path, log_path


def test_daemon_pid_helpers_remove_stale_or_invalid_pid_files(tmp_path, monkeypatch):
	pid_path, _ = _paths(tmp_path, monkeypatch)
	pid_path.parent.mkdir(parents=True)
	pid_path.write_text("not-a-pid", encoding="utf-8")
	assert daemon.is_daemon_running() is False
	assert not pid_path.exists()

	pid_path.write_text("123", encoding="utf-8")
	monkeypatch.setattr(daemon.os, "kill", lambda pid, sig: (_ for _ in ()).throw(OSError("missing")))
	assert daemon.get_daemon_pid() is None
	assert not pid_path.exists()


def test_daemon_pid_helpers_report_live_process(tmp_path, monkeypatch):
	pid_path, _ = _paths(tmp_path, monkeypatch)
	pid_path.parent.mkdir(parents=True)
	pid_path.write_text("321", encoding="utf-8")
	calls: list[tuple[int, int]] = []
	monkeypatch.setattr(daemon.os, "kill", lambda pid, sig: calls.append((pid, sig)))
	assert daemon.is_daemon_running() is True
	assert daemon.get_daemon_pid() == 321
	assert calls == [(321, 0), (321, 0)]


def test_stop_daemon_sends_sigterm_and_removes_pid_file(tmp_path, monkeypatch):
	pid_path, _ = _paths(tmp_path, monkeypatch)
	pid_path.parent.mkdir(parents=True)
	pid_path.write_text("432", encoding="utf-8")
	calls: list[tuple[int, int]] = []

	def kill(pid: int, sig: int) -> None:
		calls.append((pid, sig))
		if sig == 0 and len(calls) > 2:
			raise OSError("process exited")

	monkeypatch.setattr(daemon.os, "kill", kill)
	monkeypatch.setattr(daemon.time, "sleep", lambda seconds: None)
	assert daemon.stop_daemon() is True
	assert calls[0] == (432, 0)
	assert calls[1] == (432, signal.SIGTERM)
	assert not pid_path.exists()


def test_stop_daemon_handles_signal_failure(tmp_path, monkeypatch):
	pid_path, _ = _paths(tmp_path, monkeypatch)
	pid_path.parent.mkdir(parents=True)
	pid_path.write_text("543", encoding="utf-8")
	calls = 0

	def kill(pid: int, sig: int) -> None:
		nonlocal calls
		calls += 1
		if calls > 1:
			raise OSError("permission denied")

	monkeypatch.setattr(daemon.os, "kill", kill)
	assert daemon.stop_daemon() is False
	assert not pid_path.exists()


def test_start_daemon_background_reuses_running_daemon(tmp_path, monkeypatch):
	_paths(tmp_path, monkeypatch)
	monkeypatch.setattr(daemon, "is_daemon_running", lambda: True)
	monkeypatch.setattr(daemon, "get_daemon_pid", lambda: 654)
	monkeypatch.setattr(
		daemon.subprocess,
		"Popen",
		lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not spawn")),
	)
	assert daemon.start_daemon_background() == 654


def test_start_daemon_background_spawns_fixed_module_and_observes_pid_file(tmp_path, monkeypatch):
	pid_path, log_path = _paths(tmp_path, monkeypatch)
	monkeypatch.setattr(daemon, "is_daemon_running", lambda: False)
	monkeypatch.setattr(daemon.time, "sleep", lambda seconds: None)
	pid_values = iter((None, 765))
	monkeypatch.setattr(daemon, "get_daemon_pid", lambda: next(pid_values))
	captured: dict[str, Any] = {}

	def popen(command, **kwargs):
		captured["command"] = command
		captured["kwargs"] = kwargs
		return SimpleNamespace(pid=999)

	monkeypatch.setattr(daemon.subprocess, "Popen", popen)
	assert daemon.start_daemon_background() == 765
	assert pid_path.parent.exists()
	assert log_path.exists()
	assert captured["command"] == [
		daemon.sys.executable,
		"-m",
		"boss_agent_cli.bridge.daemon",
		"--serve",
	]
	assert captured["kwargs"]["stdin"] is daemon.subprocess.DEVNULL


def test_start_daemon_background_falls_back_to_child_pid(tmp_path, monkeypatch):
	_paths(tmp_path, monkeypatch)
	monkeypatch.setattr(daemon, "is_daemon_running", lambda: False)
	monkeypatch.setattr(daemon.time, "sleep", lambda seconds: None)
	monkeypatch.setattr(daemon, "get_daemon_pid", lambda: None)
	monkeypatch.setattr(
		daemon.subprocess,
		"Popen",
		lambda *args, **kwargs: SimpleNamespace(pid=876),
	)
	assert daemon.start_daemon_background() == 876
