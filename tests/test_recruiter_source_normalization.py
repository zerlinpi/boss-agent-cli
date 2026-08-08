from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric


def test_rank_and_report_normalize_legacy_friend_id_without_rewriting_history(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="JD", rubric=rubric)
	record = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "A"}},
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		source={"type": "zhipin", "geek_id": "g1", "friend_id": "123"},
		rubric=rubric,
	)

	ranked = store.rank(job_key="java", top=10)
	report = store.report(job_key="java", top=10)
	stored = store.get_evaluation(record["id"])

	assert ranked[0]["source"]["friend_id"] == 123
	assert report["top_candidates"][0]["source"]["friend_id"] == 123
	assert stored["source"]["friend_id"] == "123"


def test_invalid_legacy_friend_id_is_safe_for_readers(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="JD", rubric=rubric)
	store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "A"}},
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		source={"type": "zhipin", "geek_id": "g1", "friend_id": "not-an-int"},
		rubric=rubric,
	)

	assert store.rank(job_key="java", top=10)[0]["source"]["friend_id"] is None
