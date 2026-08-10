import pytest

from boss_agent_cli.web import RecruiterWebController, WebConsoleError


def test_container_login_requires_explicit_cdp(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_RECRUITER_CONTAINER", "1")
	controller = RecruiterWebController(tmp_path)

	with pytest.raises(WebConsoleError) as exc_info:
		controller.login(timeout=30)

	assert exc_info.value.code == "CONTAINER_CDP_REQUIRED"
	assert exc_info.value.status == 409


def test_container_login_forces_configured_cdp(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_RECRUITER_CONTAINER", "1")
	controller = RecruiterWebController(tmp_path, cdp_url="http://host.docker.internal:9222")
	captured = {}

	class FakeAuth:
		def login(self, **kwargs):
			captured.update(kwargs)
			return {"cookies": {"wt2": "ok"}, "_method": "CDP 扫码"}

	monkeypatch.setattr(controller, "_auth", lambda: FakeAuth())
	monkeypatch.setattr(controller, "auth_status", lambda: {"logged_in": True})

	result = controller.login(timeout=30, force_cdp=False)

	assert captured["force_cdp"] is True
	assert captured["cdp_url"] == "http://host.docker.internal:9222"
	assert result["auth"]["logged_in"] is True
