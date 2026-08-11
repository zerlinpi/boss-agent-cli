import pytest

from boss_agent_cli.web.controller import RecruiterWebController, WebConsoleError


def test_autopilot_rejects_partial_auth_before_external_work(tmp_path, monkeypatch) -> None:
	controller = RecruiterWebController(tmp_path)
	monkeypatch.setattr(controller, "operating_mode", lambda: "research")
	monkeypatch.setattr(
		controller,
		"auth_status",
		lambda: {
			"logged_in": True,
			"state": "partial",
			"summary": "degraded",
			"health": {"recovery_action": "重新登录以补全凭证"},
		},
	)

	with pytest.raises(WebConsoleError) as caught:
		controller.run_recruiter_autopilot({})

	assert caught.value.code == "AUTH_INCOMPLETE"
	assert caught.value.status == 409
	assert "重新登录以补全凭证" in str(caught.value)


def test_autopilot_requires_any_saved_login(tmp_path, monkeypatch) -> None:
	controller = RecruiterWebController(tmp_path)
	monkeypatch.setattr(controller, "operating_mode", lambda: "research")
	monkeypatch.setattr(
		controller,
		"auth_status",
		lambda: {"logged_in": False, "state": "missing", "summary": "missing", "health": {}},
	)

	with pytest.raises(WebConsoleError) as caught:
		controller.run_recruiter_autopilot({})

	assert caught.value.code == "AUTH_REQUIRED"
	assert caught.value.status == 409
