from boss_agent_cli.web import RecruiterWebController
from boss_agent_cli.web.server import RecruiterWebApplication


def test_app_asset_defers_screen_result_context_guard_until_all_wrappers_load(tmp_path) -> None:
	application = RecruiterWebApplication(RecruiterWebController(tmp_path), token="fixed")
	try:
		content, content_type = application.asset("app.js")
		text = content.decode("utf-8")
		assert content_type.startswith("text/javascript")
		assert 'window.addEventListener("load"' in text
		assert "contextAwareScreenResult" in text
		assert "resultJob !== state.activeJob" in text
		assert "可在任务与审计中查看结果" in text
	finally:
		application.tasks.close()
