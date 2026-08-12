from importlib.resources import files
from types import SimpleNamespace
from typing import Any

import boss_agent_cli.web.ui_extension as ui_extension


class _FakeApplication:
	def asset(self, name: str) -> tuple[bytes, str]:
		if name == "app.js":
			return b"// base app\n", "application/javascript"
		return b"", "application/octet-stream"


def test_guided_setup_is_appended_to_web_app_asset(monkeypatch: Any) -> None:
	monkeypatch.setattr(ui_extension, "_INSTALLED", False)
	server_module = SimpleNamespace(RecruiterWebApplication=_FakeApplication)
	ui_extension.install_ui_reliability_assets(server_module)

	content, content_type = _FakeApplication().asset("app.js")
	text = content.decode("utf-8")

	assert content_type == "application/javascript"
	assert "第一次使用只完成这 4 步" in text
	assert "下一步：运行 5 人安全测试" in text
	assert "#autopilot-max-candidates" in text


def test_guided_setup_keeps_first_run_small_and_research_explicit() -> None:
	text = files("boss_agent_cli.web.assets").joinpath("guided_setup.js").read_text(encoding="utf-8")

	assert '"#autopilot-max-pages": "1"' in text
	assert '"#autopilot-max-candidates": "5"' in text
	assert '"#autopilot-refresh-hours": "0"' in text
	assert '"#autopilot-draft-top": "2"' in text
	assert "请选择 Research，并确认已获得候选人数据处理授权" in text
	assert 'setMode("research")' not in text
	assert "创建岗位" not in text


def test_guided_setup_prioritizes_autopilot_and_collapses_secondary_screening() -> None:
	text = files("boss_agent_cli.web.assets").joinpath("guided_setup.js").read_text(encoding="utf-8")

	assert 'grid.prepend(autopilot)' in text
	assert 'details.id = "advanced-screening-options"' in text
	assert "主流程优先使用全职位 Autopilot" in text
	assert "本地文件 / 单岗位" in text


def test_guided_setup_keeps_only_core_navigation_visible_by_default() -> None:
	text = files("boss_agent_cli.web.assets").joinpath("guided_setup.js").read_text(encoding="utf-8")

	assert '["dashboard", "screening", "pipeline", "replies", "settings"]' in text
	assert '["jobs", "activity"]' in text
	assert 'toggle.id = "product-advanced-toggle"' in text
	assert "高级功能" in text
	assert "岗位与规则" in text
	assert "自动筛选" in text


def test_primary_action_tracks_the_next_required_step() -> None:
	text = files("boss_agent_cli.web.assets").joinpath("guided_setup.js").read_text(encoding="utf-8")

	for label in ("配置 AI", "登录 BOSS", "启用 Research", "运行 5 人验证", "运行 Autopilot"):
		assert label in text
	assert "data-product-primary-action" in text
	assert 'picker.classList.toggle("hidden", !state.jobs.length)' in text
