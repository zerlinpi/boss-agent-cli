from unittest.mock import MagicMock

import pytest

import boss_agent_cli.api.zhilian_reliability as reliability
from boss_agent_cli.api.zhilian_client import ZhilianClient


class Auth:
	def __init__(self, token=None):
		self.token = token or {"cookies": {"zp_token": "token"}, "user_agent": "UA"}
		self.refreshes = 0

	def get_token(self):
		return self.token

	def force_refresh(self, cdp_url=None):
		self.refreshes += 1


class Response:
	text = ""

	def __init__(self, status_code, payload):
		self.status_code = status_code
		self.payload = payload

	def raise_for_status(self):
		return None

	def json(self):
		if isinstance(self.payload, Exception):
			raise self.payload
		return self.payload


class HttpClient:
	def __init__(self, responses):
		self.responses = iter(responses)
		self.headers_seen = []

	def request(self, method, url, headers=None, **kwargs):
		self.headers_seen.append(dict(headers or {}))
		return next(self.responses)


def test_auth_retry_preserves_and_refreshes_csrf_header(monkeypatch) -> None:
	auth = Auth()
	client = ZhilianClient(auth, delay=(0, 0))
	http = HttpClient([
		Response(401, {"code": 401}),
		Response(200, {"code": 200, "data": {}}),
	])
	client._get_client = MagicMock(return_value=http)
	client._merge_cookies = MagicMock()
	client.get_csrf_token = MagicMock(return_value="csrf-new")
	client._throttle.wait = MagicMock()
	client._throttle.mark = MagicMock()
	monkeypatch.setattr(reliability.time, "sleep", lambda seconds: None)
	monkeypatch.setattr(reliability.random, "uniform", lambda a, b: 0.0)

	result = client._request("POST", "https://example.invalid/write", headers={"csrf-token": "csrf-old"})

	assert result["code"] == 200
	assert auth.refreshes == 1
	assert http.headers_seen[0]["csrf-token"] == "csrf-old"
	assert http.headers_seen[1]["csrf-token"] == "csrf-new"
	client.get_csrf_token.assert_called_once_with(force_refresh=True)


def test_invalid_zhilian_json_is_a_controlled_runtime_error() -> None:
	client = ZhilianClient(Auth(), delay=(0, 0))
	http = HttpClient([Response(200, ValueError("bad json"))])
	client._get_client = MagicMock(return_value=http)
	client._merge_cookies = MagicMock()
	client._throttle.wait = MagicMock()
	client._throttle.mark = MagicMock()

	with pytest.raises(RuntimeError, match="不是有效 JSON"):
		client._request("GET", "https://example.invalid/read")


def test_corrupt_zhilian_cookie_shape_is_rejected_before_client_creation() -> None:
	client = ZhilianClient(Auth({"cookies": []}), delay=(0, 0))
	with pytest.raises(RuntimeError, match="cookies 不是对象"):
		client._get_client()
