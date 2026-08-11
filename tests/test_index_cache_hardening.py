import json

from boss_agent_cli.index_cache import get_index_info, get_job_by_index, save_index


def test_index_cache_rejects_non_object_json(tmp_path) -> None:
	path = tmp_path / "cache" / "index_cache.json"
	path.parent.mkdir(parents=True)
	path.write_text("[]", encoding="utf-8")

	assert get_job_by_index(tmp_path, 1) is None
	assert get_index_info(tmp_path) == {"exists": False, "source": "", "count": 0, "saved_at": 0}


def test_index_cache_rejects_invalid_jobs_shape(tmp_path) -> None:
	path = tmp_path / "cache" / "index_cache.json"
	path.parent.mkdir(parents=True)
	path.write_text(json.dumps({"jobs": ["bad"]}), encoding="utf-8")

	assert get_job_by_index(tmp_path, 1) is None


def test_index_cache_metadata_count_comes_from_validated_jobs(tmp_path) -> None:
	save_index(tmp_path, [{"job_id": "job-1", "title": "Engineer"}], source="search")
	path = tmp_path / "cache" / "index_cache.json"
	payload = json.loads(path.read_text(encoding="utf-8"))
	payload["count"] = 999
	path.write_text(json.dumps(payload), encoding="utf-8")

	assert get_job_by_index(tmp_path, 1)["job_id"] == "job-1"
	assert get_index_info(tmp_path)["count"] == 1


def test_index_cache_atomic_write_leaves_no_temp_files(tmp_path) -> None:
	save_index(tmp_path, [{"job_id": "job-1"}])
	assert (tmp_path / "cache" / "index_cache.json").is_file()
	assert not list((tmp_path / "cache").glob(".index_cache.json.*.tmp"))
