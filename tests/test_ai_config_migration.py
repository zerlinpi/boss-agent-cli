from cryptography.fernet import Fernet

from boss_agent_cli.ai.config import AIConfigStore


def test_legacy_ai_key_is_migrated_to_shared_machine_identity(tmp_path, monkeypatch) -> None:
	monkeypatch.delenv("BOSS_AGENT_MACHINE_ID", raising=False)
	store = AIConfigStore(tmp_path)
	monkeypatch.setattr(AIConfigStore, "_get_machine_id", lambda self: "stable-machine")
	monkeypatch.setattr(AIConfigStore, "_legacy_machine_id", lambda self: "legacy-machine")

	legacy_key = store._derive_key_for_machine_id("legacy-machine")
	store._key_path.write_bytes(Fernet(legacy_key).encrypt(b"sk-legacy"))

	assert store.get_api_key() == "sk-legacy"

	migrated = store._key_path.read_bytes()
	current_key = store._derive_key_for_machine_id("stable-machine")
	assert Fernet(current_key).decrypt(migrated) == b"sk-legacy"


def test_local_ai_provider_can_target_docker_host(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_AGENT_MACHINE_ID", "test-machine")
	monkeypatch.setenv("BOSS_LOCAL_AI_HOST", "host.docker.internal")
	store = AIConfigStore(tmp_path)

	store.save_config(ai_provider="ollama")
	assert store.get_base_url() == "http://host.docker.internal:11434/v1"

	store.save_config(ai_provider="vllm")
	assert store.get_base_url() == "http://host.docker.internal:8000/v1"
