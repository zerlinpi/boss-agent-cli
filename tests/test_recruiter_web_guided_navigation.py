from importlib.resources import files
from types import SimpleNamespace
from typing import Any

import boss_agent_cli.web.ui_extension as ui_extension


class _FakeApplication:
	def asset(self, name: str) -> tuple[bytes, str]:
		if name == "app.js":
			return b"// base app\n", "application/javascript"
		return b"", "application/octet-stream"


def test_guided_navigation_is_appended_after_guided_setup(monkeypatch: Any) -> None:
	monkeypatch.setattr(ui_extension, "_INSTALLED", False)
	server_module = SimpleNamespace(RecruiterWebApplication=_FakeApplication)
	ui_extension.install_ui_reliability_assets(server_module)

	content, content_type = _FakeApplication().asset("app.js")
	text = content.decode("utf-8")

	assert content_type == "application/javascript"
	assert 'const PRIMARY_VIEWS = ["dashboard", "screening", "pipeline", "replies", "settings"]' in text
	assert text.index("第一次使用只完成这 4 步") < text.index("const PRIMARY_VIEWS")


def test_guided_navigation_shortcuts_match_visible_product_navigation() -> None:
	text = files("boss_agent_cli.web.assets").joinpath("guided_navigation.js").read_text(encoding="utf-8")

	assert 'const PRIMARY_VIEWS = ["dashboard", "screening", "pipeline", "replies", "settings"]' in text
	assert 'item.setAttribute("aria-keyshortcuts", String(index + 1))' in text
	assert 'setView(PRIMARY_VIEWS[index])' in text
	assert "event.stopImmediatePropagation()" in text
	assert 'item.setAttribute("aria-current", "page")' in text
	assert 'button.setAttribute("aria-pressed", String(button.classList.contains("active")))' in text
