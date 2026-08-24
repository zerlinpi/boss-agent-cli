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


def test_feedback_assets_are_appended_to_recruiter_web(monkeypatch: Any) -> None:
	monkeypatch.setattr(ui_extension, "_INSTALLED", False)
	server_module = SimpleNamespace(RecruiterWebApplication=_FakeApplication)
	ui_extension.install_ui_reliability_assets(server_module)

	app_js, app_type = _FakeApplication().asset("app.js")
	styles, styles_type = _FakeApplication().asset("styles.css")

	assert app_type == "application/javascript"
	assert styles_type == "text/css"
	assert b"candidate-workbench-status" in app_js
	assert b"task-recovery-panel" in app_js
	assert b"autopilot-result-heading" in app_js
	assert b"candidate-workbench-status" in styles
	assert b"task-recovery-panel" in styles


def test_candidate_feedback_distinguishes_no_data_from_no_filter_matches() -> None:
	text = files("boss_agent_cli.web.assets").joinpath("guided_feedback.js").read_text(encoding="utf-8")

	assert "当前岗位暂无候选人" in text
	assert "没有符合当前筛选条件的候选人" in text
	assert "运行 Autopilot 同步最新投递" in text
	assert "清除筛选" in text
	assert 'node.setAttribute("aria-live", "polite")' in text
	assert 'node.setAttribute("aria-busy", String(busy))' in text


def test_failed_tasks_offer_recovery_without_auto_retry() -> None:
	text = files("boss_agent_cli.web.assets").joinpath("guided_feedback.js").read_text(encoding="utf-8")

	for code in ("AUTH_REQUIRED", "AUTH_INCOMPLETE", "COMPLIANCE_BLOCKED", "SCREENING_ALREADY_RUNNING"):
		assert code in text
	for label in ("重新登录 BOSS", "检查 Research", "检查 AI 配置", "查看运行任务", "返回自动筛选"):
		assert label in text
	assert 'panel.setAttribute("role", "alert")' in text
	assert 'data-feedback-action="${recovery.action}"' in text
	assert "autopilot-run-button.click" not in text


def test_autopilot_result_feedback_points_to_human_review_next_steps() -> None:
	text = files("boss_agent_cli.web.assets").joinpath("guided_autopilot_feedback.js").read_text(encoding="utf-8")

	assert "已进入人工复核" in text
	assert "AI 不会自动做最终招聘决定" in text
	assert 'data-autopilot-result-action="candidates"' in text
	assert 'data-autopilot-result-action="replies"' in text
	assert 'data-autopilot-result-action="failures"' in text
	assert 'setView("pipeline")' in text
	assert 'setView("replies")' in text
	assert "runAutopilot(" not in text
