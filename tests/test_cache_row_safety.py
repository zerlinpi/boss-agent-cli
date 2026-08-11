import pytest

from boss_agent_cli.cache import CacheRowCorruptionError, CacheStore


def test_corrupt_crawl_run_params_fails_with_controlled_error(tmp_path) -> None:
	with CacheStore(tmp_path / "cache.db") as store:
		store.create_crawl_run("run-1", {"query": "python"}, str(tmp_path / "out"))
		store._conn.execute("UPDATE crawl_runs SET params = ? WHERE run_id = ?", ("{bad-json", "run-1"))
		store._conn.commit()

		with pytest.raises(CacheRowCorruptionError, match="crawl_runs.params"):
			store.get_crawl_run("run-1")


def test_corrupt_crawl_run_hook_results_shape_fails_closed(tmp_path) -> None:
	with CacheStore(tmp_path / "cache.db") as store:
		store.create_crawl_run("run-1", {"query": "python"}, str(tmp_path / "out"))
		store._conn.execute("UPDATE crawl_runs SET hook_results = ? WHERE run_id = ?", ("{}", "run-1"))
		store._conn.commit()

		with pytest.raises(CacheRowCorruptionError, match="hook_results"):
			store.get_crawl_run("run-1")


def test_corrupt_crawl_job_payload_fails_with_row_identity(tmp_path) -> None:
	with CacheStore(tmp_path / "cache.db") as store:
		store.create_crawl_run("run-1", {"query": "python"}, str(tmp_path / "out"))
		store.put_crawl_job("run-1", "job-1", 1, {"title": "Engineer"}, detail_done=False)
		store._conn.execute(
			"UPDATE crawl_jobs SET payload = ? WHERE run_id = ? AND job_key = ?",
			("[]", "run-1", "job-1"),
		)
		store._conn.commit()

		with pytest.raises(CacheRowCorruptionError, match="job_key=job-1"):
			store.get_crawl_job("run-1", "job-1")
		with pytest.raises(CacheRowCorruptionError, match="job_key=job-1"):
			store.list_crawl_jobs("run-1")
