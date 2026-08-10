"""Tests for AI service client."""

import math
from unittest.mock import MagicMock, patch

import httpx
import pytest

from boss_agent_cli.ai.service import AIService, AIServiceError


def _make_service(**kwargs) -> AIService:
	defaults = {
		"base_url": "https://api.example.com/v1",
		"api_key": "sk-test-key",
		"model": "gpt-4",
		"temperature": 0.7,
		"max_tokens": 4096,
	}
	defaults.update(kwargs)
	return AIService(**defaults)


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
	"""Create a mock httpx.Response."""
	if json_data is None:
		json_data = {"choices": [{"message": {"content": "Hello, world!"}}]}
	return httpx.Response(
		status_code=status_code,
		json=json_data,
		request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
	)


@patch("boss_agent_cli.ai.service.httpx.post")
def test_chat_success(mock_post):
	mock_post.return_value = _mock_response(200, {"choices": [{"message": {"content": "Test reply"}}]})
	service = _make_service()
	assert service.chat([{"role": "user", "content": "Hi"}]) == "Test reply"


@patch("boss_agent_cli.ai.service.httpx.post")
def test_chat_request_headers(mock_post):
	mock_post.return_value = _mock_response()
	service = _make_service(api_key="sk-my-key")
	service.chat([{"role": "user", "content": "Hi"}])
	headers = mock_post.call_args.kwargs["headers"]
	assert headers["Authorization"] == "Bearer sk-my-key"
	assert headers["Content-Type"] == "application/json"


@patch("boss_agent_cli.ai.service.httpx.post")
def test_chat_request_body(mock_post):
	mock_post.return_value = _mock_response()
	service = _make_service(model="gpt-4o", temperature=0.5, max_tokens=2048)
	service.chat([{"role": "user", "content": "Hello"}])
	payload = mock_post.call_args.kwargs["json"]
	assert payload["model"] == "gpt-4o"
	assert payload["messages"] == [{"role": "user", "content": "Hello"}]
	assert payload["temperature"] == 0.5
	assert payload["max_tokens"] == 2048


@patch("boss_agent_cli.ai.service.httpx.post")
def test_chat_url_construction(mock_post):
	mock_post.return_value = _mock_response()
	service = _make_service(base_url="https://api.example.com/v1")
	service.chat([{"role": "user", "content": "Hi"}])
	assert mock_post.call_args.args[0] == "https://api.example.com/v1/chat/completions"


@patch("boss_agent_cli.ai.service.httpx.post")
def test_chat_http_401(mock_post):
	mock_post.return_value = _mock_response(401, {"error": {"message": "Unauthorized"}})
	service = _make_service()
	with pytest.raises(AIServiceError) as exc_info:
		service.chat([{"role": "user", "content": "Hi"}])
	assert exc_info.value.status_code == 401


@patch("boss_agent_cli.ai.service.httpx.post")
def test_chat_http_500(mock_post):
	mock_post.return_value = _mock_response(500, {"error": {"message": "Internal Server Error"}})
	service = _make_service()
	with pytest.raises(AIServiceError) as exc_info:
		service.chat([{"role": "user", "content": "Hi"}])
	assert exc_info.value.status_code == 500


@patch("boss_agent_cli.ai.service.httpx.post")
def test_chat_network_error(mock_post):
	mock_post.side_effect = httpx.ConnectError("Connection refused")
	service = _make_service()
	with pytest.raises(AIServiceError) as exc_info:
		service.chat([{"role": "user", "content": "Hi"}])
	assert exc_info.value.status_code is None
	assert "网络请求失败" in str(exc_info.value)


@patch("boss_agent_cli.ai.service.httpx.post")
def test_chat_malformed_response(mock_post):
	mock_post.return_value = _mock_response(200, {"unexpected": "format"})
	service = _make_service()
	with pytest.raises(AIServiceError) as exc_info:
		service.chat([{"role": "user", "content": "Hi"}])
	assert "响应格式异常" in str(exc_info.value)


@patch("boss_agent_cli.ai.service.httpx.post")
def test_chat_empty_choices(mock_post):
	mock_post.return_value = _mock_response(200, {"choices": []})
	service = _make_service()
	with pytest.raises(AIServiceError) as exc_info:
		service.chat([{"role": "user", "content": "Hi"}])
	assert "响应格式异常" in str(exc_info.value)


@patch("boss_agent_cli.ai.service.httpx.post")
def test_chat_non_json_response_uses_ai_error_contract(mock_post):
	response = MagicMock()
	response.raise_for_status.return_value = None
	response.json.side_effect = ValueError("not json")
	mock_post.return_value = response
	with pytest.raises(AIServiceError, match="不是有效 JSON"):
		_make_service().chat([{"role": "user", "content": "Hi"}])


@patch("boss_agent_cli.ai.service.httpx.post")
def test_chat_non_string_content_is_rejected(mock_post):
	mock_post.return_value = _mock_response(200, {"choices": [{"message": {"content": None}}]})
	with pytest.raises(AIServiceError, match="content 必须是字符串"):
		_make_service().chat([{"role": "user", "content": "Hi"}])


@patch("boss_agent_cli.ai.service.httpx.post")
def test_chat_temperature_override(mock_post):
	mock_post.return_value = _mock_response()
	service = _make_service(temperature=0.7)
	service.chat([{"role": "user", "content": "Hi"}], temperature=0.2)
	assert mock_post.call_args.kwargs["json"]["temperature"] == 0.2


@patch("boss_agent_cli.ai.service.httpx.post")
def test_chat_max_tokens_override(mock_post):
	mock_post.return_value = _mock_response()
	service = _make_service(max_tokens=4096)
	service.chat([{"role": "user", "content": "Hi"}], max_tokens=1024)
	assert mock_post.call_args.kwargs["json"]["max_tokens"] == 1024


@patch("boss_agent_cli.ai.service.httpx.post")
def test_chat_base_url_trailing_slash(mock_post):
	mock_post.return_value = _mock_response()
	service = _make_service(base_url="https://api.example.com/v1/")
	service.chat([{"role": "user", "content": "Hi"}])
	url = mock_post.call_args.args[0]
	assert url == "https://api.example.com/v1/chat/completions"
	assert "//" not in url.replace("https://", "")


@pytest.mark.parametrize("base_url", ["file:///tmp/model", "localhost:8000/v1", "http://user:pass@localhost:8000/v1"])
def test_service_rejects_invalid_base_urls(base_url):
	with pytest.raises(AIServiceError):
		_make_service(base_url=base_url)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 2.1, True])
def test_service_rejects_invalid_temperature(value):
	with pytest.raises(AIServiceError):
		_make_service(temperature=value)


@pytest.mark.parametrize("value", [0, -1, True])
def test_service_rejects_invalid_max_tokens(value):
	with pytest.raises(AIServiceError):
		_make_service(max_tokens=value)


def test_service_rejects_empty_key_model_or_messages():
	with pytest.raises(AIServiceError):
		_make_service(api_key="")
	with pytest.raises(AIServiceError):
		_make_service(model="")
	with pytest.raises(AIServiceError):
		_make_service().chat([])
	with pytest.raises(AIServiceError):
		_make_service().chat([{"role": "user", "content": None}])  # type: ignore[list-item]


def test_service_rejects_oversized_configuration_fields():
	with pytest.raises(AIServiceError, match="Base URL 过长"):
		_make_service(base_url="https://example.com/" + "a" * 2050)
	with pytest.raises(AIServiceError, match="API Key 过长"):
		_make_service(api_key="k" * 8193)
	with pytest.raises(AIServiceError, match="模型名称过长"):
		_make_service(model="m" * 257)


@patch("boss_agent_cli.ai.service.httpx.post")
def test_service_rejects_oversized_messages_before_network_call(mock_post):
	service = _make_service()
	with pytest.raises(AIServiceError, match="最多 100 条"):
		service.chat([{"role": "user", "content": "x"}] * 101)
	with pytest.raises(AIServiceError, match="500000 字符"):
		service.chat([{"role": "user", "content": "x" * 500001}])
	with pytest.raises(AIServiceError, match="1000000 字符"):
		service.chat([
			{"role": "system", "content": "x" * 500000},
			{"role": "user", "content": "y" * 500000},
			{"role": "user", "content": "z"},
		])
	mock_post.assert_not_called()


def test_service_accepts_finite_temperature_boundaries():
	for value in (0, 0.5, 2):
		service = _make_service(temperature=value)
		assert math.isfinite(service.temperature)
