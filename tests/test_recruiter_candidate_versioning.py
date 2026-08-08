from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric


def test_latest_candidate_uses_absolute_time_across_timezone_offsets(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	resume = {"basic": {"name": "候选人A"}, "raw_text": "Java"}
	source = {"type": "zhipin", "geek_id": "g1"}

	first = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume=resume,
		evaluation={"total_score": 70, "recommendation": "interview", "confidence": 0.8},
		source=source,
		rubric=rubric,
	)
	second = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume=resume,
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		source=source,
		rubric=rubric,
	)

	# 12:00 +08:00 == 04:00 UTC, so the second record at 05:00 UTC is the real latest record.
	first["created_at"] = "2026-08-08T12:00:00+08:00"
	second["created_at"] = "2026-08-08T05:00:00+00:00"
	store._write(store.evaluations_dir / f"{first['id']}.json", first)
	store._write(store.evaluations_dir / f"{second['id']}.json", second)

	latest = store.latest_by_candidate(job_key="java")
	assert len(latest) == 1
	assert next(iter(latest.values()))["id"] == second["id"]


def test_latest_candidate_accepts_z_and_naive_legacy_timestamps(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	resume = {"basic": {"name": "候选人A"}, "raw_text": "Java"}
	source = {"type": "zhipin", "geek_id": "g1"}
	older = store.save_evaluation(
		job_key="java", jd_text="JD", resume=resume,
		evaluation={"total_score": 70, "recommendation": "interview", "confidence": 0.8},
		source=source, rubric=rubric,
	)
	newer = store.save_evaluation(
		job_key="java", jd_text="JD", resume=resume,
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		source=source, rubric=rubric,
	)
	older["created_at"] = "2026-08-08T04:00:00Z"
	newer["created_at"] = "2026-08-08T05:00:00"
	store._write(store.evaluations_dir / f"{older['id']}.json", older)
	store._write(store.evaluations_dir / f"{newer['id']}.json", newer)

	assert next(iter(store.latest_by_candidate(job_key="java").values()))["id"] == newer["id"]
