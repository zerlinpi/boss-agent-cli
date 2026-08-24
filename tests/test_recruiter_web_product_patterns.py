from importlib.resources import files
from types import SimpleNamespace
from typing import Any

import boss_agent_cli.web.ui_extension as ui_extension


class _FakeApplication:
	def asset(self, name: str) -> tuple[bytes, str]:
		if name == "app.js":
			return b"// base app\n", "application/javascript"
		if name == "styles.css":
			return b"/* base styles */\n", "text/css"
		return b"", "application/octet-stream"


def test_product_workbench_assets_are_appended(monkeypatch: Any) -> None:
	monkeypatch.setattr(ui_extension, "_INSTALLED", False)
	server_module = SimpleNamespace(RecruiterWebApplication=_FakeApplication)
	ui_extension.install_ui_reliability_assets(server_module)

	js, js_type = _FakeApplication().asset("app.js")
	css, css_type = _FakeApplication().asset("styles.css")
	js_text = js.decode("utf-8")
	css_text = css.decode("utf-8")

	assert js_type == "application/javascript"
	assert css_type == "text/css"
	assert "今日待处理" in js_text
	assert "人工审核队列" in js_text
	assert "运行前检查" in js_text
	assert ".product-ops-workbench" in css_text
	assert ".product-human-decision-section" in css_text
	assert js_text.index("boss-autopilot-first-run-defaults") < js_text.index("今日待处理")
	assert css_text.index(".autopilot-panel::before") < css_text.index(".product-ops-workbench")


def test_product_workbench_keeps_explainable_human_review_boundary() -> None:
	assets = files("boss_agent_cli.web.assets")
	js = assets.joinpath("product_workbench.js").read_text(encoding="utf-8")
	css = assets.joinpath("product_workbench.css").read_text(encoding="utf-8")

	for marker in (
		"INTERVIEW_RECOMMENDATIONS",
		"product_interview_any",
		"建议面试（含强烈）",
		"人工审核队列",
		"自动发送消息：0",
		"最终判断",
		"人工确认",
		"renderCandidateDrawer = function productRenderCandidateDrawer",
	):
		assert marker in js

	assert "不要仅依据总分做最终招聘决定" in js
	assert ".product-evidence-rail" in css
	assert ".autopilot-run-plan" in css
	assert "@media (max-width: 850px)" in css
	assert "@media (prefers-reduced-motion: reduce)" in css
