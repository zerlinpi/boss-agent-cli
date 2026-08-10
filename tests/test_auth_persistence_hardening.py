import os
import stat
from pathlib import Path

from boss_agent_cli.auth.token_store import TokenStore


def test_auth_files_are_owner_only_on_posix(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_AGENT_MACHINE_ID", "test-machine")
	store = TokenStore(tmp_path)
	store.save({"cookies": {"wt2": "secret"}})

	if os.name != "nt":
		assert stat.S_IMODE((tmp_path / "salt").stat().st_mode) == 0o600
		assert stat.S_IMODE((tmp_path / "session.enc").stat().st_mode) == 0o600


def test_truncated_salt_invalidates_broken_session_and_recovers(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_AGENT_MACHINE_ID", "test-machine")
	store = TokenStore(tmp_path)
	(tmp_path / "salt").write_bytes(b"short")
	(tmp_path / "session.enc").write_bytes(b"old-session")

	assert store.load() is None
	assert len((tmp_path / "salt").read_bytes()) >= 16
	assert not (tmp_path / "session.enc").exists()


def test_session_read_io_error_is_treated_as_logged_out(tmp_path, monkeypatch) -> None:
	monkeypatch.setenv("BOSS_AGENT_MACHINE_ID", "test-machine")
	store = TokenStore(tmp_path)
	store.save({"cookies": {"wt2": "secret"}})
	original_read_bytes = Path.read_bytes

	def read_bytes(path: Path) -> bytes:
		if path == store._session_path:
			raise OSError("simulated read failure")
		return original_read_bytes(path)

	monkeypatch.setattr(Path, "read_bytes", read_bytes)
	assert store.load() is None
