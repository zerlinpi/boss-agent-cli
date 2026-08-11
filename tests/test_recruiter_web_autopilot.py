import time
from pathlib import Path

import pytest

from boss_agent_cli.web import RecruiterWebController, WebConsoleError, build_server


def test_web_autopilot_assets_and_empty_status(tmp_path: Path):
	controller = RecruiterWebController(tmp_path)
	server, app = build_server(controller, port=0)
	try:
		status = controller.autopilot_status()
		assert status == {"last_run": None, "tracked_candidates": 0}
		app_js, _ = app.asset("app.js")
		styles, _ = app.asset("styles.css")
		assert b"autopilot-run-button" in app_js
		assert b"Recruiter Autopilot" in app_js
		assert b"autopilot-panel" in styles
	finally:
		app.tasks.close()
		server.server_close()


def test_web_autopilot_route_runs_as_background_task(monkeypatch, tmp_path: Path):
	controller = RecruiterWebController(tmp_path)
	server, app = build_server(controller, port=0)
	try:
		def fake_run(payload, *, progress=None):
			assert payload["max_pages"] == 7
			if progress:
				progress(75, "fake progress")
			return {
				"totals": {"jobs_processed": 2, "evaluated": 4, "failed": 0},
				"messages_sent": 0,
				"final_employment_decisions_automated": False,
				"human_review_required": True,
			}

		monkeypatch.setattr(controller, "run_recruiter_autopilot", fake_run)
		task = app.post("/api/autopilot/run", {"max_pages": 7})
		assert task["kind"] == "autopilot"
		deadline = time.time() + 3
		completed = None
		while time.time() < deadline:
			completed = app.tasks.get(task["id"])
			if completed and completed["status"] in {"completed", "failed"}:
				break
			time.sleep(0.01)
		assert completed is not None
		assert completed["status"] == "completed"
		assert completed["result"]["messages_sent"] == 0
		assert completed["result"]["final_employment_decisions_automated"] is False
	finally:
		app.tasks.close()
		server.server_close()


def test_web_autopilot_refuses_to_overlap_other_screening(monkeypatch, tmp_path: Path):
	controller = RecruiterWebController(tmp_path)
	server, app = build_server(controller, port=0)
	try:
		monkeypatch.setattr(app.tasks, "has_active_screening", lambda *_args, **_kwargs: True)
		with pytest.raises(WebConsoleError) as exc_info:
			app.post("/api/autopilot/run", {})
		assert exc_info.value.code == "SCREENING_ALREADY_RUNNING"
		assert exc_info.value.status == 409
	finally:
		app.tasks.close()
		server.server_close()
