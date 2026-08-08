from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric


def test_store_report_scans_evaluation_history_once(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="JD", rubric=rubric)
	for index in range(3):
		store.save_evaluation(
			job_key="java",
			jd_text="JD",
			resume={"basic": {"name": f"候选人{index}"}},
			evaluation={"total_score": 70 + index, "recommendation": "interview", "confidence": 0.8},
			source={"type": "zhipin", "geek_id": f"g{index}"},
			rubric=rubric,
		)

	original_list = store.list_evaluations
	calls = 0

	def counted_list(*, job_key=None):
		nonlocal calls
		calls += 1
		return original_list(job_key=job_key)

	store.list_evaluations = counted_list  # type: ignore[method-assign]
	report = store.report(job_key="java", top=2)

	assert report["total_candidates"] == 3
	assert len(report["top_candidates"]) == 2
	assert calls == 1
