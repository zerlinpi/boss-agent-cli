import math

import pytest

from boss_agent_cli.web import RecruiterWebController, WebConsoleError


def _payload(**overrides):
	payload = {
		"provider": "custom",
		"model": "test-model",
		"base_url": "https://proxy.example/v1",
		"api_key": "test-key",
		"temperature": 0.2,
		"max_tokens": 4096,
	}
	payload.update(overrides)
	return payload


def test_web_ai_invalid_url_is_rejected_before_any_config_write(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	with pytest.raises(WebConsoleError) as captured:
		controller.configure_ai(_payload(base_url="not-a-url"))
	assert captured.value.code == "INVALID_AI_CONFIG"
	assert not controller.ai_store._config_path.exists()
	assert not controller.ai_store._key_path.exists()


def test_web_ai_nonfinite_temperature_is_rejected_before_write(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	with pytest.raises(WebConsoleError) as captured:
		controller.configure_ai(_payload(temperature=math.nan))
	assert captured.value.code == "INVALID_AI_CONFIG"
	assert not controller.ai_store._config_path.exists()


def test_web_ai_fractional_max_tokens_is_rejected(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	with pytest.raises(WebConsoleError) as captured:
		controller.configure_ai(_payload(max_tokens="4096.5"))
	assert captured.value.code == "INVALID_AI_CONFIG"
