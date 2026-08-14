from importlib.resources import files
from types import SimpleNamespace
from typing import Any

import boss_agent_cli.web.ui_extension as ui_extension


class _FakeApplication:
	def asset(self, name: str) -> tuple[bytes, str]:
		if name == "styles.css":
			return b"/* base styles */\n", "text/css"
		return b"", "application/octet-stream"


def test_guided_visual_css_is_appended_after_feedback_styles(monkeypatch: Any) -> None:
	monkeypatch.setattr(ui_extension, "_INSTALLED", False)
	server_module = SimpleNamespace(RecruiterWebApplication=_FakeApplication)
	ui_extension.install_ui_reliability_assets(server_module)

	content, content_type = _FakeApplication().asset("styles.css")
	text = content.decode("utf-8")

	assert content_type == "text/css"
	assert ".candidate-workbench-status" in text
	assert ".autopilot-panel::before" in text
	assert text.index(".candidate-workbench-status") < text.index(".autopilot-panel::before")


def test_guided_visual_css_covers_core_recruiter_surfaces_and_accessibility() -> None:
	text = files("boss_agent_cli.web.assets").joinpath("guided_visual.css").read_text(encoding="utf-8")

	for selector in (
		".sidebar",
		".topbar",
		".metric-card",
		".onboarding",
		".autopilot-panel",
		".filter-toolbar",
		".table-card",
		".reply-card",
		".settings-grid",
		".drawer-panel",
	):
		assert selector in text
	assert 'tbody tr:has(input[type="checkbox"]:checked)' in text
	assert "@media (max-width: 850px)" in text
	assert "@media (prefers-reduced-motion: reduce)" in text
	assert "transition-duration: .01ms !important" in text
