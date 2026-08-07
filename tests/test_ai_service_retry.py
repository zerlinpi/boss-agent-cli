from unittest.mock import patch

import httpx
import pytest

from boss_agent_cli.ai.service import AIService, AIServiceError


def _service() -> AIService:
	return AIService(
		base_url="https://api.example.com/v1",
		api_key="key",
		model="model",
		temperature=0.2,
		max_tokens=256,
	)


def _response(status: int, payload=None, headers=None) -> httpx.Response:
	return httpx.Response(
		status_code=status,
		json=payload or {"choices": [{"message": {"content": "ok"}}]},
		headers=headers,
		request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
	)


def test_retryable_http_status_is_retried_then_succeeds() -> None:
	with (
		patch("boss_agent_cli.ai.service.httpx.post", side_effect=[_response(503), _response(200)]) as post,
		patch("boss_agent_cli.ai.service.time.sleep") as sleep,
	):
		result = _service().chat([{"role": "user", "content": "hello"}])

	assert result == "ok"
	assert post.call_count == 2
	sleep.assert_called_once_with(0.5)


def test_retry_after_header_is_respected_with_bounded_delay() -> None:
	with (
		patch(
			"boss_agent_cli.ai.service.httpx.post",
			side_effect=[_response(429, headers={"Retry-After": "1.25"}), _response(200)],
		),
		patch("boss_agent_cli.ai.service.time.sleep") as sleep,
	):
		_service().chat([{"role": "user", "content": "hello"}])

	sleep.assert_called_once_with(1.25)


def test_auth_error_is_not_retried() -> None:
	with patch("boss_agent_cli.ai.service.httpx.post", return_value=_response(401)) as post:
		with pytest.raises(AIServiceError) as caught:
			_service().chat([{"role": "user", "content": "hello"}])

	assert caught.value.status_code == 401
	assert post.call_count == 1


def test_connect_error_is_retried_but_read_timeout_is_not() -> None:
	request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
	with (
		patch(
			"boss_agent_cli.ai.service.httpx.post",
			side_effect=[httpx.ConnectError("refused", request=request), _response(200)],
		) as post,
		patch("boss_agent_cli.ai.service.time.sleep"),
	):
		assert _service().chat([{"role": "user", "content": "hello"}]) == "ok"
		assert post.call_count == 2

	with patch(
		"boss_agent_cli.ai.service.httpx.post",
		side_effect=httpx.ReadTimeout("read timeout", request=request),
	) as post:
		with pytest.raises(AIServiceError):
			_service().chat([{"role": "user", "content": "hello"}])
		assert post.call_count == 1
