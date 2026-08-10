import pytest

import boss_agent_cli.web.container_auth as container_auth
from boss_agent_cli.auth.manager import AuthManager, TokenRefreshFailed
from boss_agent_cli.web import RecruiterWebController, WebConsoleError


def test_container_login_requires_explicit_cdp(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_RECRUITER_CONTAINER", "1")
	monkeypatch.delenv("BOSS_CDP_URL", raising=False)
	controller = RecruiterWebController(tmp_path)

	status = controller.auth_status()
	assert status["container_cdp_required"] is True
	assert "BOSS_CDP_URL" in status["summary"]

	with pytest.raises(WebConsoleError) as exc_info:
		controller.login(timeout=30)

	assert exc_info.value.code == "CONTAINER_CDP_REQUIRED"
	assert exc_info.value.status == 409


def test_container_logged_in_status_warns_about_future_refresh(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_RECRUITER_CONTAINER", "1")
	monkeypatch.delenv("BOSS_CDP_URL", raising=False)
	controller = RecruiterWebController(tmp_path)

	class FakeAuth:
		def check_status(self):
			return {"cookies": {"wt2": "ok"}}

	monkeypatch.setattr(controller, "_auth", lambda: FakeAuth())
	status = controller.auth_status()

	assert status["logged_in"] is True
	assert status["container_cdp_required"] is True
	assert "刷新" in status["summary"]
	assert "BOSS_CDP_URL" in status["summary"]


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


def test_container_refresh_requires_cdp(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_RECRUITER_CONTAINER", "1")
	monkeypatch.delenv("BOSS_CDP_URL", raising=False)
	auth = AuthManager(tmp_path)

	with pytest.raises(TokenRefreshFailed, match="BOSS_CDP_URL"):
		auth.force_refresh()


def test_container_refresh_rejects_unreachable_cdp(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_RECRUITER_CONTAINER", "1")
	monkeypatch.setenv("BOSS_CDP_URL", "http://host.docker.internal:9222")
	monkeypatch.setattr(container_auth, "probe_cdp", lambda url: None)
	auth = AuthManager(tmp_path)

	with pytest.raises(TokenRefreshFailed, match="不可达"):
		auth.force_refresh()
