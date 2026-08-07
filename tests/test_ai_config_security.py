from __future__ import annotations

import json
import os

import pytest

from boss_agent_cli.ai.config import AIConfigStore


def _store(tmp_path, monkeypatch):
	monkeypatch.setenv("BOSS_AGENT_MACHINE_ID", "security-test-machine")
	return AIConfigStore(tmp_path)


def test_ai_sensitive_files_use_private_permissions_on_posix(tmp_path, monkeypatch):
	store = _store(tmp_path, monkeypatch)
	store.save_config(ai_provider="openai", ai_model="gpt-4o")
	store.save_api_key("secret")

	if os.name != "nt":
		for path in (
			tmp_path / "ai" / "config.json",
			tmp_path / "ai" / "api_key.enc",
			tmp_path / "auth" / "salt",
		):
			assert path.stat().st_mode & 0o777 == 0o600


def test_ai_config_ignores_valid_json_with_wrong_top_level_type(tmp_path, monkeypatch):
	store = _store(tmp_path, monkeypatch)
	config_path = tmp_path / "ai" / "config.json"
	config_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
	config = store.load_config()
	assert config["ai_provider"] is None
	assert config["ai_model"] is None
	assert config["ai_max_tokens"] == 4096


def test_ai_config_filters_unknown_fields_from_existing_file(tmp_path, monkeypatch):
	store = _store(tmp_path, monkeypatch)
	config_path = tmp_path / "ai" / "config.json"
	config_path.write_text(json.dumps({"ai_provider": "openai", "api_key": "plaintext-secret"}), encoding="utf-8")
	config = store.load_config()
	assert config["ai_provider"] == "openai"
	assert "api_key" not in config


def test_ai_config_rejects_unknown_fields_on_write(tmp_path, monkeypatch):
	store = _store(tmp_path, monkeypatch)
	with pytest.raises(ValueError, match="unknown AI config fields"):
		store.save_config(api_key="must-not-be-plaintext")
	assert not (tmp_path / "ai" / "config.json").exists()


def test_corrupt_empty_salt_invalidates_old_api_key_cleanly(tmp_path, monkeypatch):
	store = _store(tmp_path, monkeypatch)
	store.save_api_key("secret")
	(tmp_path / "auth" / "salt").write_bytes(b"")

	fresh_store = _store(tmp_path, monkeypatch)
	assert fresh_store.get_api_key() is None
	assert (tmp_path / "auth" / "salt").stat().st_size >= 16
	assert not (tmp_path / "ai" / "api_key.enc").exists()


def test_ai_atomic_writes_leave_no_temp_files(tmp_path, monkeypatch):
	store = _store(tmp_path, monkeypatch)
	store.save_config(ai_provider="deepseek")
	store.save_api_key("secret")
	assert list((tmp_path / "ai").glob(".*.tmp")) == []
