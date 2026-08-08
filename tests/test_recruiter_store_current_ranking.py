import pytest

from boss_agent_cli.recruiter_ai import RecruiterAIError, RecruiterAIStore, normalize_rubric


def _evaluation(score: int):
	return {
		"total_score": score,
		"recommendation": "interview",
		"confidence": 0.8,
		"dimensions": [],
		"strengths": [],
		"concerns": [],
		"next_questions": [],
		"summary": f"score {score}",
	}


def test_store_rank_and_report_exclude_old_saved_job_results(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="旧 JD", rubric=rubric)
	store.save_evaluation(
		job_key="java", jd_text="旧 JD", resume={"basic": {"name": "A"}},
		evaluation=_evaluation(80), source={"type": "zhipin", "geek_id": "g1"}, rubric=rubric,
	)
	store.save_job(job_key="java", jd_text="新 JD", rubric=rubric)

	assert store.rank(job_key="java", top=10) == []
	report = store.report(job_key="java", top=10)
	assert report["total_candidates"] == 0
	assert report["stale_count"] == 1
	assert report["top_candidates"] == []


def test_store_rank_restores_candidate_after_current_job_reevaluation(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="旧 JD", rubric=rubric)
	store.save_evaluation(
		job_key="java", jd_text="旧 JD", resume={"basic": {"name": "A"}, "raw_text": "v1"},
		evaluation=_evaluation(70), source={"type": "zhipin", "geek_id": "g1"}, rubric=rubric,
	)
	store.save_job(job_key="java", jd_text="新 JD", rubric=rubric)
	current = store.save_evaluation(
		job_key="java", jd_text="新 JD", resume={"basic": {"name": "A"}, "raw_text": "v2"},
		evaluation=_evaluation(90), source={"type": "zhipin", "geek_id": "g1"}, rubric=rubric,
	)

	assert [record["id"] for record in store.rank(job_key="java", top=10)] == [current["id"]]
	report = store.report(job_key="java", top=10)
	assert report["total_candidates"] == 1
	assert report["stale_count"] == 0


def test_ad_hoc_rank_without_saved_job_keeps_latest_results(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	record = store.save_evaluation(
		job_key="adhoc", jd_text="临时 JD", resume={"basic": {"name": "A"}},
		evaluation=_evaluation(80), source={"type": "local", "input": "inline"}, rubric=rubric,
	)

	assert [item["id"] for item in store.rank(job_key="adhoc", top=10)] == [record["id"]]
	report = store.report(job_key="adhoc", top=10)
	assert report["total_candidates"] == 1
	assert report["stale_count"] == 0


def test_corrupt_saved_job_never_falls_back_to_historical_ranking(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="JD", rubric=rubric)
	store.save_evaluation(
		job_key="java", jd_text="JD", resume={"basic": {"name": "A"}},
		evaluation=_evaluation(80), source={"type": "zhipin", "geek_id": "g1"}, rubric=rubric,
	)
	(store.jobs_dir / "java.json").write_text("{not-json", encoding="utf-8")

	with pytest.raises(RecruiterAIError, match="岗位配置损坏"):
		store.rank(job_key="java", top=10)
	with pytest.raises(RecruiterAIError, match="岗位配置损坏"):
		store.report(job_key="java", top=10)
