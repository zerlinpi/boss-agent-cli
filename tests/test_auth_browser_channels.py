from types import SimpleNamespace

import pytest

from boss_agent_cli.auth.browser import _launch_chromium


class _Chromium:
	def __init__(self, *, available: str | None = None) -> None:
		self.available = available
		self.calls: list[dict[str, object]] = []

	def launch(self, **kwargs):
		self.calls.append(kwargs)
		channel = kwargs.get("channel")
		if channel == self.available:
			return channel
		if channel is None and self.available == "bundled":
			return "bundled"
		raise RuntimeError("not available")


def test_launch_chromium_prefers_installed_edge_after_chrome() -> None:
	chromium = _Chromium(available="msedge")
	playwright = SimpleNamespace(chromium=chromium)

	result = _launch_chromium(playwright, headless=False)

	assert result == "msedge"
	assert chromium.calls == [
		{"channel": "chrome", "headless": False},
		{"channel": "msedge", "headless": False},
	]


def test_launch_chromium_keeps_patchright_runtime_as_final_fallback() -> None:
	chromium = _Chromium(available="bundled")
	playwright = SimpleNamespace(chromium=chromium)

	assert _launch_chromium(playwright, headless=True) == "bundled"
	assert chromium.calls[-1] == {"headless": True}


def test_launch_chromium_reports_actionable_error_when_no_browser_exists() -> None:
	chromium = _Chromium(available=None)
	playwright = SimpleNamespace(chromium=chromium)

	with pytest.raises(RuntimeError, match="Chrome/Edge/Chromium"):
		_launch_chromium(playwright, headless=False)
