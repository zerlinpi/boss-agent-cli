from boss_agent_cli.web import RecruiterWebController
from boss_agent_cli.web.server import RecruiterWebApplication


def test_web_bundle_contains_stale_result_warning_assets_once(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	application = RecruiterWebApplication(controller, token="fixed")
	try:
		javascript, js_type = application.asset("app.js")
		styles, css_type = application.asset("styles.css")
		js = javascript.decode("utf-8")
		css = styles.decode("utf-8")
		assert js_type.startswith("text/javascript") or "javascript" in js_type
		assert css_type.startswith("text/css")
		assert js.count("stale-results-dashboard") == 1
		assert js.count("旧评估已从当前排名、统计和 CSV 中排除") == 1
		assert "data-stale-open-screening" in js
		assert css.count(".stale-results-warning {") == 1
	finally:
		application.tasks.close()
