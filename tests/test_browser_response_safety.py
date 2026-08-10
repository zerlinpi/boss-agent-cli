import pytest

from boss_agent_cli.api.browser_response_safety import install_browser_response_safety


class GoodSession:
	def request(self, method, url, **kwargs):
		return {"code": 0, "zpData": {}}


class BadSession:
	def request(self, method, url, **kwargs):
		return ["unexpected"]


def test_browser_response_guard_preserves_object_payloads() -> None:
	install_browser_response_safety(GoodSession)
	assert GoodSession().request("GET", "/resource")["code"] == 0


def test_browser_response_guard_rejects_non_object_payloads() -> None:
	install_browser_response_safety(BadSession)
	with pytest.raises(RuntimeError, match="期望 JSON object"):
		BadSession().request("GET", "/resource")
