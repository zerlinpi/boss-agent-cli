from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric


def test_recruiter_store_public_methods_and_record_shape(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	for name in (
		"save_job",
		"get_job",
		"list_jobs",
		"save_evaluation",
		"get_evaluation",
		"list_evaluations",
		"latest_by_candidate",
		"find_unchanged",
		"rank",
		"set_status",
		"save_reply",
		"report",
	):
		assert callable(getattr(store, name, None)), name

	rubric = normalize_rubric()
	job = store.save_job(job_key="java", jd_text="Java JD", rubric=rubric)
	assert job["rubric"] == rubric
	assert job["updated_at"]

	record = store.save_evaluation(
		job_key="java",
		jd_text="Java JD",
		resume={"basic": {"name": "张三"}, "work_experience": [{"company": "Example"}]},
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		source={"type": "local", "path": "resume.json"},
		rubric=rubric,
	)
	assert record["created_at"]
	assert record["updated_at"]
	assert record["rubric"] == rubric
	assert record["rubric_fingerprint"]
	assert record["source"]["path"] == "resume.json"

	listed = store.list_evaluations(job_key="java")
	assert [item["id"] for item in listed] == [record["id"]]
	assert store.rank(job_key="java", top=0) == []

	updated = store.set_status(record["id"], "interview", note="人工确认")
	assert updated["status"] == "interview"
	assert updated["status_note"] == "人工确认"
	assert updated["updated_at"]


def test_find_unchanged_accepts_optional_source_and_preserves_incremental_contract(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	resume = {"basic": {"name": "张三"}}
	record = store.save_evaluation(
		job_key="java",
		jd_text="Java JD",
		resume=resume,
		evaluation={"total_score": 70, "recommendation": "interview", "confidence": 0.7},
		source=None,
		rubric=rubric,
	)
	unchanged = store.find_unchanged(job_key="java", resume=resume, source=None, rubric=rubric)
	assert unchanged is not None
	assert unchanged["id"] == record["id"]
