import sqlite3

import pytest

from boss_agent_cli.cache.store import CacheStore


def test_corrupt_cache_database_is_quarantined_and_rebuilt(tmp_path) -> None:
	db_path = tmp_path / "cache.db"
	db_path.write_bytes(b"this is not sqlite")

	store = CacheStore(db_path)
	try:
		assert db_path.exists()
		assert list(tmp_path.glob("cache.db.corrupt-*"))
		row = store._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='search_cache'").fetchone()
		assert row == ("search_cache",)
	finally:
		store.close()


def test_non_corruption_database_errors_are_not_quarantined(tmp_path, monkeypatch) -> None:
	db_path = tmp_path / "cache.db"
	original_connect = sqlite3.connect

	def locked(*args, **kwargs):
		raise sqlite3.OperationalError("database is locked")

	monkeypatch.setattr(sqlite3, "connect", locked)
	with pytest.raises(sqlite3.OperationalError, match="locked"):
		CacheStore(db_path)
	assert not list(tmp_path.glob("*.corrupt-*"))
	monkeypatch.setattr(sqlite3, "connect", original_connect)
