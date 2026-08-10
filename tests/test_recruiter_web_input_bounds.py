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
		("max_tokens", 4096.5),
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


def test_ai_settings_reject_objects_and_arrays_in_text_fields(tmp_path):
	controller = RecruiterWebController(tmp_path)
	base = {"provider": "deepseek", "model": "deepseek-chat", "api_key": "key"}
	for field, value in (
		("provider", ["deepseek"]),
		("model", {"name": "deepseek-chat"}),
		("api_key", ["key"]),
		("base_url", {"url": "https://api.example.com/v1"}),
	):
		with pytest.raises(WebConsoleError) as caught:
			controller.configure_ai({**base, field: value})
		assert caught.value.code in {"INVALID_PARAM", "INVALID_BASE_URL"}


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


def test_job_save_rejects_non_string_text_fields(tmp_path):
	controller = RecruiterWebController(tmp_path)
	with pytest.raises(WebConsoleError) as caught:
		controller.save_job({"job_key": "backend", "title": ["Backend"], "jd_text": "valid JD"})
	assert caught.value.code == "INVALID_PARAM"


def test_boss_screen_rejects_fractional_or_structured_parameters_before_platform_access(tmp_path):
	controller = RecruiterWebController(tmp_path)
	controller.save_job({"job_key": "backend", "title": "Backend", "jd_text": "valid JD"})
	for payload in (
		{"job_key": "backend", "job_id": "job-1", "pages": 1.5},
		{"job_key": "backend", "job_id": {"id": "job-1"}},
		{"job_key": "backend", "job_id": "job-1", "limit": [30]},
	):
		with pytest.raises(WebConsoleError) as caught:
			controller.screen_boss(payload)
		assert caught.value.code == "INVALID_PARAM"


def test_reply_generation_rejects_structured_chat_context(tmp_path):
	controller = RecruiterWebController(tmp_path)
	with pytest.raises(WebConsoleError) as caught:
		controller.generate_reply({"evaluation_id": "eval_missing", "intent": "acknowledge", "conversation": ["hello"]})
	assert caught.value.code == "INVALID_PARAM"
