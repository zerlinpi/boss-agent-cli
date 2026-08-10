import pytest

from boss_agent_cli.api._base_client import _BaseHttpClient


class BoundaryAuthError(Exception):
	pass


class FakeAuth:
	def __init__(self, token):
		self.token = token

	def get_token(self):
		return self.token

	def force_refresh(self, cdp_url=None):
		return None


class TestClient(_BaseHttpClient):
	_BASE_URL = "https://example.invalid"
	_DEFAULT_HEADERS = {}
	_REFERER_MAP = {}
	_AUTH_ERROR_CLS = BoundaryAuthError
	_CODE_STOKEN_EXPIRED = 37
	_CODE_RATE_LIMITED = 9


class Response:
	status_code = 200
	text = ""

	def __init__(self, payload):
		self.payload = payload

	def raise_for_status(self):
		return None

	def json(self):
		if isinstance(self.payload, Exception):
			raise self.payload
		return self.payload


class HttpClient:
	def __init__(self, payload):
		self.payload = payload

	def request(self, *args, **kwargs):
		return Response(self.payload)

	def close(self):
		return None


def _client(token, payload):
	client = TestClient(FakeAuth(token), delay=(0, 0))
	client._client = HttpClient(payload)
	client._merge_cookies = lambda response: None
	return client


def test_corrupt_cookie_shape_is_rejected_before_network_use() -> None:
	client = TestClient(FakeAuth({"cookies": []}), delay=(0, 0))
	with pytest.raises(BoundaryAuthError, match="cookies 不是对象"):
		client._get_client()


def test_empty_cookie_object_is_rejected_before_network_use() -> None:
	client = TestClient(FakeAuth({"cookies": {}}), delay=(0, 0))
	with pytest.raises(BoundaryAuthError, match="缺少有效 Cookie"):
		client._get_client()


def test_non_object_json_response_becomes_controlled_platform_error() -> None:
	client = _client({"cookies": {"wt2": "ok"}}, ["unexpected"])
	with pytest.raises(BoundaryAuthError, match="非对象 JSON"):
		client._request("GET", "/resource")


def test_invalid_json_response_becomes_controlled_platform_error() -> None:
	client = _client({"cookies": {"wt2": "ok"}}, ValueError("bad json"))
	with pytest.raises(BoundaryAuthError, match="无法解析"):
		client._request("GET", "/resource")
