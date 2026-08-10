import os

from boss_agent_cli.auth.token_store import TokenStore
from boss_agent_cli.web.container_main import _ensure_persistent_machine_id


def test_container_machine_identity_is_persisted_and_reused(tmp_path, monkeypatch) -> None:
	monkeypatch.delenv("BOSS_AGENT_MACHINE_ID", raising=False)
	monkeypatch.setattr(TokenStore, "_get_machine_id", lambda self: "legacy-container-machine")

	assert _ensure_persistent_machine_id(tmp_path) == "legacy-container-machine"
	assert os.environ["BOSS_AGENT_MACHINE_ID"] == "legacy-container-machine"
	identity_path = tmp_path / "auth" / "container-machine-id"
	assert identity_path.read_text(encoding="utf-8") == "legacy-container-machine"

	monkeypatch.delenv("BOSS_AGENT_MACHINE_ID", raising=False)
	monkeypatch.setattr(TokenStore, "_get_machine_id", lambda self: "new-ephemeral-machine")
	assert _ensure_persistent_machine_id(tmp_path) == "legacy-container-machine"
	assert os.environ["BOSS_AGENT_MACHINE_ID"] == "legacy-container-machine"


def test_explicit_container_machine_identity_wins(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_AGENT_MACHINE_ID", "operator-supplied-machine")
	assert _ensure_persistent_machine_id(tmp_path) == "operator-supplied-machine"
	assert not (tmp_path / "auth" / "container-machine-id").exists()
