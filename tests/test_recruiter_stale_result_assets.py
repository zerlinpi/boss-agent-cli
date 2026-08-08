from boss_agent_cli.web import RecruiterWebController
from boss_agent_cli.web.server import RecruiterWebApplication


def test_web_bundle_contains_stale_result_warning_assets(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	application = RecruiterWebApplication(controller, token="fixed")
	try:
		javascript, js_type = application.asset("app.js")
		styles, css_type = application.asset("styles.css")
		js = javascript.decode("utf-8")
		css = styles.decode("utf-8")
		assert js_type.startswith("text/javascript") or "javascript" in js_type
		assert css_type.startswith("text/css")
		assert "stale-results-dashboard" in js
		assert "旧评估已从当前排名、统计和 CSV 中排除" in js
		assert "data-stale-open-screening" in js
		assert ".stale-results-warning" in css
	finally:
		application.tasks.close()
