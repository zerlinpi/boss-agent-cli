import math

import pytest

from boss_agent_cli.ai.config import AIConfigStore


def _store(tmp_path, monkeypatch) -> AIConfigStore:
	monkeypatch.setenv("BOSS_AGENT_MACHINE_ID", "validation-machine")
	return AIConfigStore(tmp_path)


def test_invalid_ai_base_url_is_rejected_before_persistence(tmp_path, monkeypatch) -> None:
	store = _store(tmp_path, monkeypatch)
	with pytest.raises(ValueError, match="HTTP"):
		store.save_config(ai_provider="custom", ai_model="model", ai_base_url="not-a-url")
	assert not store._config_path.exists()


def test_unknown_ai_provider_is_rejected(tmp_path, monkeypatch) -> None:
	store = _store(tmp_path, monkeypatch)
	with pytest.raises(ValueError, match="provider"):
		store.save_config(ai_provider="unknown-provider")


def test_nonfinite_temperature_is_rejected(tmp_path, monkeypatch) -> None:
	store = _store(tmp_path, monkeypatch)
	with pytest.raises(ValueError, match="temperature"):
		store.save_config(ai_temperature=math.nan)
	with pytest.raises(ValueError, match="temperature"):
		store.save_config(ai_temperature=math.inf)


def test_boolean_max_tokens_is_rejected(tmp_path, monkeypatch) -> None:
	store = _store(tmp_path, monkeypatch)
	with pytest.raises(ValueError, match="max_tokens"):
		store.save_config(ai_max_tokens=True)


def test_empty_api_key_is_rejected_without_key_file(tmp_path, monkeypatch) -> None:
	store = _store(tmp_path, monkeypatch)
	with pytest.raises(ValueError, match="不能为空"):
		store.save_api_key("  ")
	assert not store._key_path.exists()


def test_valid_custom_configuration_roundtrips(tmp_path, monkeypatch) -> None:
	store = _store(tmp_path, monkeypatch)
	store.save_config(
		ai_provider="custom",
		ai_model="my-model",
		ai_base_url="https://proxy.example/v1/",
		ai_temperature=0.2,
		ai_max_tokens=4096,
	)
	config = store.load_config()
	assert config["ai_base_url"] == "https://proxy.example/v1"
