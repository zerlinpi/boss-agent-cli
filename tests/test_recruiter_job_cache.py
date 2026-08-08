import json
import os

from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric


def test_job_cache_reuses_saved_profile_without_re_reading_file(tmp_path, monkeypatch) -> None:
	store = RecruiterAIStore(tmp_path)
	store.save_job(job_key="java", jd_text="旧 JD", rubric=normalize_rubric())
	path = store.jobs_dir / "java.json"
	original_read_text = type(path).read_text
	reads = 0

	def counted_read_text(self, *args, **kwargs):
		nonlocal reads
		if self == path:
			reads += 1
		return original_read_text(self, *args, **kwargs)

	monkeypatch.setattr(type(path), "read_text", counted_read_text)
	assert store.get_job("java")["jd_text"] == "旧 JD"
	assert store.get_job("java")["jd_text"] == "旧 JD"
	assert reads == 0


def test_job_cache_invalidates_after_external_file_change(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	record = store.save_job(job_key="java", jd_text="旧 JD", rubric=normalize_rubric())
	path = store.jobs_dir / "java.json"
	before = path.stat().st_mtime_ns
	updated = dict(record)
	updated["jd_text"] = "外部修改后的 JD"
	path.write_text(json.dumps(updated, ensure_ascii=False), encoding="utf-8")
	os.utime(path, ns=(before + 2_000_000_000, before + 2_000_000_000))

	assert store.get_job("java")["jd_text"] == "外部修改后的 JD"


def test_job_cache_returns_independent_objects(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	store.save_job(job_key="java", jd_text="Java JD", rubric=normalize_rubric())
	first = store.get_job("java")
	first["jd_text"] = "调用方修改"

	assert store.get_job("java")["jd_text"] == "Java JD"
