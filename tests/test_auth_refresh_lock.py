import os
import time

import pytest

import boss_agent_cli.auth.token_store as token_store_module
from boss_agent_cli.auth.manager import AuthManager, TokenRefreshFailed
from boss_agent_cli.auth.token_store import RefreshLockBusy, TokenStore


def test_live_refresh_lock_is_not_stolen_after_wait_timeout(tmp_path, monkeypatch) -> None:
	store = TokenStore(tmp_path)
	store._lock_path.write_text("owner", encoding="utf-8")
	monkeypatch.setattr(token_store_module, "_LOCK_TIMEOUT", 0)

	with pytest.raises(RefreshLockBusy):
		with store.refresh_lock():
			pass

	assert store._lock_path.exists()


def test_stale_refresh_lock_is_recovered(tmp_path, monkeypatch) -> None:
	store = TokenStore(tmp_path)
	store._lock_path.write_text("stale", encoding="utf-8")
	old = time.time() - token_store_module._STALE_LOCK_SECONDS - 10
	os.utime(store._lock_path, (old, old))
	monkeypatch.setattr(token_store_module, "_LOCK_TIMEOUT", 0)

	with store.refresh_lock():
		assert store._lock_path.exists()

	assert not store._lock_path.exists()


def test_auth_manager_surfaces_busy_refresh_as_token_refresh_failure(tmp_path, monkeypatch) -> None:
	auth = AuthManager(tmp_path)

	class BusyLock:
		def __enter__(self):
			raise RefreshLockBusy("已有登录态刷新任务正在运行，请稍后重试")

		def __exit__(self, exc_type, exc, tb):
			return False

	monkeypatch.setattr(auth._store, "refresh_lock", lambda: BusyLock())
	with pytest.raises(TokenRefreshFailed, match="已有登录态刷新任务"):
		auth.force_refresh()
