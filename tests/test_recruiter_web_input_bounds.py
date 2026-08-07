import pytest

from boss_agent_cli.web import RecruiterWebController, WebConsoleError
from boss_agent_cli.web.reliability import MAX_API_KEY_CHARS, MAX_JD_CHARS, MAX_MODEL_NAME_CHARS


def test_ai_settings_reject_non_finite_or_out_of_range_numbers(tmp_path):
	controller = RecruiterWebController(tmp_path)
	base = {"provider": "deepseek", "model": "deepseek-chat", "api_key": "key"}
	for field, value in (
		("temperature", float("nan")),
		("temperature", float("inf")),
		("temperature", 2.1),
		("max_tokens", True),
		("max_tokens", 255),
		("max_tokens", 32769),
	):
		with pytest.raises(WebConsoleError) as caught:
			controller.configure_ai({**base, field: value})
		assert caught.value.code == "INVALID_PARAM"


def test_ai_settings_reject_invalid_or_embedded_credential_base_urls(tmp_path):
	controller = RecruiterWebController(tmp_path)
	base = {"provider": "custom", "model": "custom-model", "api_key": "key"}
	for base_url in ("file:///tmp/model", "localhost:8000/v1", "http://user:pass@localhost:8000/v1"):
		with pytest.raises(WebConsoleError) as caught:
			controller.configure_ai({**base, "base_url": base_url})
		assert caught.value.code == "INVALID_BASE_URL"


def test_ai_settings_reject_unreasonably_large_secrets_and_model_names(tmp_path):
	controller = RecruiterWebController(tmp_path)
	with pytest.raises(WebConsoleError):
		controller.configure_ai({
			"provider": "deepseek",
			"model": "m" * (MAX_MODEL_NAME_CHARS + 1),
			"api_key": "key",
		})
	with pytest.raises(WebConsoleError):
		controller.configure_ai({
			"provider": "deepseek",
			"model": "deepseek-chat",
			"api_key": "k" * (MAX_API_KEY_CHARS + 1),
		})


def test_job_save_and_analysis_reject_oversized_jd_before_storage_or_model_call(tmp_path):
	controller = RecruiterWebController(tmp_path)
	oversized = "J" * (MAX_JD_CHARS + 1)
	with pytest.raises(WebConsoleError) as caught:
		controller.save_job({"job_key": "backend", "title": "Backend", "jd_text": oversized})
	assert caught.value.code == "INVALID_PARAM"
	assert controller.list_jobs() == []

	with pytest.raises(WebConsoleError) as caught:
		controller.analyze_job({"jd_text": oversized})
	assert caught.value.code == "INVALID_PARAM"
