import httpx
import pytest

import boss_agent_cli.auth.manager as auth_module
from boss_agent_cli.auth.manager import AuthManager


def test_default_login_uses_visible_browser_when_cookie_and_cdp_are_unavailable(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_AGENT_MACHINE_ID", "test-machine")
	auth = AuthManager(tmp_path)
	events = []
	monkeypatch.setattr(auth_module, "extract_cookies", lambda *args, **kwargs: None)
	monkeypatch.setattr(auth_module, "probe_cdp", lambda *args, **kwargs: None)

	def browser(**kwargs):
		events.append("browser")
		return {"cookies": {"wt2": "ok"}, "stoken": "browser"}

	monkeypatch.setattr(auth_module, "login_via_browser", browser)
	result = auth.login(timeout=30)

	assert result["_method"] == "扫码登录"
	assert events == ["browser"]


def test_visible_browser_failure_is_surfaced_without_hidden_qr_wait(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_AGENT_MACHINE_ID", "test-machine")
	auth = AuthManager(tmp_path)
	monkeypatch.setattr(auth_module, "extract_cookies", lambda *args, **kwargs: None)
	monkeypatch.setattr(auth_module, "probe_cdp", lambda *args, **kwargs: None)

	def browser(**kwargs):
		raise RuntimeError("browser unavailable")

	monkeypatch.setattr(auth_module, "login_via_browser", browser)
	with pytest.raises(RuntimeError, match="browser unavailable"):
		auth.login(timeout=30)


def test_malformed_cookie_container_is_rejected_without_exception(tmp_path) -> None:
	auth = AuthManager(tmp_path)
	assert auth._has_primary_cookie({"cookies": []}) is False
	assert auth._verify_cookie({"cookies": []}) is False


def test_non_object_user_info_response_is_treated_as_invalid_cookie(tmp_path, monkeypatch) -> None:
	auth = AuthManager(tmp_path)

	class Response:
		def json(self):
			return ["unexpected"]

	monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: Response())
	assert auth._verify_cookie({"cookies": {"wt2": "ok"}}) is False
