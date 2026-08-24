import sys
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import Any

import boss_agent_cli.desktop as desktop


class _FakeTasks:
	def __init__(self) -> None:
		self.closed = False

	def close(self) -> None:
		self.closed = True


class _FakeServer:
	def __init__(self) -> None:
		self.server_port = 43123
		self.stopped = Event()
		self.closed = False

	def serve_forever(self, *, poll_interval: float) -> None:
		assert poll_interval == 0.25
		self.stopped.wait(timeout=2)

	def shutdown(self) -> None:
		self.stopped.set()

	def server_close(self) -> None:
		self.closed = True


def test_desktop_uses_ephemeral_loopback_server_and_closes_cleanly(monkeypatch: Any, tmp_path: Path) -> None:
	server = _FakeServer()
	tasks = _FakeTasks()
	application = SimpleNamespace(tasks=tasks)
	captured: dict[str, Any] = {}

	class FakeController:
		def __init__(self, data_dir: Path, *, platform: str, cdp_url: str | None) -> None:
			captured["controller"] = (data_dir, platform, cdp_url)

	def fake_build_server(controller: Any, *, host: str, port: int):
		captured["server"] = (controller, host, port)
		return server, application

	fake_webview = SimpleNamespace(
		create_window=lambda title, **kwargs: captured.update({"window": (title, kwargs)}),
		start=lambda **kwargs: captured.update({"start": kwargs}),
	)
	monkeypatch.setattr(desktop, "RecruiterWebController", FakeController)
	monkeypatch.setattr(desktop, "build_server", fake_build_server)
	monkeypatch.setitem(sys.modules, "webview", fake_webview)

	desktop.run_desktop(data_dir=tmp_path, platform="zhipin", cdp_url=None, width=1200, height=760)

	assert captured["server"][1:] == ("127.0.0.1", 0)
	assert captured["window"][0] == "Boss Recruit AI"
	assert captured["window"][1]["url"] == "http://127.0.0.1:43123/"
	assert captured["window"][1]["min_size"] == (980, 680)
	assert captured["start"] == {"debug": False}
	assert tasks.closed is True
	assert server.closed is True
	assert server.stopped.is_set()
