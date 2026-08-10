from boss_agent_cli.web import RecruiterWebController
from boss_agent_cli.web.server import RecruiterWebApplication


def test_recruiter_app_asset_contains_write_deduplication_keyboard_freshness_and_multi_task_polling(tmp_path) -> None:
	application = RecruiterWebApplication(RecruiterWebController(tmp_path), token="fixed")
	try:
		content, content_type = application.asset("app.js")
		text = content.decode("utf-8")

		assert content_type.startswith("text/javascript")
		assert "inFlightWrites" in text
		assert "reliableApi" in text
		assert "taskPollers" in text
		assert "multiTaskWatch" in text
		assert "latestWatchedTask" in text
		assert "accessibleRenderKanban" in text
		assert "aria-label" in text
		assert 'event.key === "Escape"' in text
		assert "drawerReturnFocus" in text
		assert "candidate-freshness-warning" in text
		assert "当前查看的是历史评估" in text
		assert "打开最新评估" in text
	finally:
		application.tasks.close()
