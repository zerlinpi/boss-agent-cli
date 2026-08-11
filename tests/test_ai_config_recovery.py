import json
import math

from cryptography.fernet import Fernet

from boss_agent_cli.ai.config import AIConfigStore


def test_legacy_malformed_fields_are_sanitized_independently(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_AGENT_MACHINE_ID", "recovery-machine")
	store = AIConfigStore(tmp_path)
	store._config_path.write_text(json.dumps({
		"ai_provider": "ollama",
		"ai_model": ["bad"],
		"ai_base_url": "not-a-url",
		"ai_temperature": float("nan"),
		"ai_max_tokens": -1,
	}), encoding="utf-8")

	config = store.load_config()
	assert config["ai_provider"] == "ollama"
	assert config["ai_model"] is None
	assert config["ai_base_url"] is None
	assert config["ai_temperature"] == 0.7
	assert config["ai_max_tokens"] == 4096
	assert math.isfinite(config["ai_temperature"])
	assert store.get_base_url() == "http://localhost:11434/v1"


def test_unknown_legacy_provider_does_not_poison_other_valid_fields(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_AGENT_MACHINE_ID", "recovery-machine")
	store = AIConfigStore(tmp_path)
	store._config_path.write_text(json.dumps({
		"ai_provider": "unknown",
		"ai_model": "valid-model",
		"ai_temperature": 0.2,
	}), encoding="utf-8")

	config = store.load_config()
	assert config["ai_provider"] is None
	assert config["ai_model"] == "valid-model"
	assert config["ai_temperature"] == 0.2


def test_decrypted_oversized_api_key_is_treated_as_unusable(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_AGENT_MACHINE_ID", "recovery-machine")
	store = AIConfigStore(tmp_path)
	store._key_path.write_bytes(Fernet(store._derive_key()).encrypt(("x" * 9000).encode("utf-8")))
	assert store.get_api_key() is None


def test_decrypted_empty_api_key_is_treated_as_unusable(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_AGENT_MACHINE_ID", "recovery-machine")
	store = AIConfigStore(tmp_path)
	store._key_path.write_bytes(Fernet(store._derive_key()).encrypt(b"   "))
	assert store.get_api_key() is None
