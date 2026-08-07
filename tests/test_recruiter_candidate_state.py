from pathlib import Path

from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric


def _evaluation(score: int):
	return {
		"total_score": score,
		"confidence": 0.8,
		"recommendation": "interview",
		"dimensions": [],
		"strengths": [],
		"concerns": [],
		"next_questions": [],
		"summary": "",
	}


def test_re_evaluation_preserves_recruiter_stage_and_note(tmp_path: Path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	source = {"type": "zhipin", "geek_id": "g1"}
	first = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "候选人A"}, "raw_text": "Java 5 years"},
		evaluation=_evaluation(70),
		source=source,
		rubric=rubric,
	)
	store.set_status(first["id"], "interview", note="技术初面已安排")

	second = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "候选人A"}, "raw_text": "Java 6 years; new project"},
		evaluation=_evaluation(85),
		source=source,
		rubric=rubric,
	)

	assert second["id"] != first["id"]
	assert second["status"] == "interview"
	assert second["status_note"] == "技术初面已安排"
	latest = store.latest_by_candidate(job_key="java")
	assert len(latest) == 1
	assert next(iter(latest.values()))["id"] == second["id"]


def test_re_evaluation_preserves_note_while_candidate_is_still_new(tmp_path: Path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	source = {"type": "zhipin", "geek_id": "g1"}
	first = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "候选人A"}, "raw_text": "Java 5 years"},
		evaluation=_evaluation(70),
		source=source,
		rubric=rubric,
	)
	store.set_status(first["id"], "new", note="等待业务负责人补充岗位要求")

	second = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "候选人A"}, "raw_text": "Java 6 years; new project"},
		evaluation=_evaluation(85),
		source=source,
		rubric=rubric,
	)

	assert second["status"] == "new"
	assert second["status_note"] == "等待业务负责人补充岗位要求"


def test_legacy_local_content_keys_are_canonicalized_by_source_path(tmp_path: Path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	source = {"type": "local", "path": str(tmp_path / "candidate.json")}
	first = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "候选人A"}, "raw_text": "old"},
		evaluation=_evaluation(60),
		source=source,
		rubric=rubric,
	)
	# Simulate a pre-stable-identity record already persisted on disk.
	path = store.evaluations_dir / f"{first['id']}.json"
	payload = store.get_evaluation(first["id"])
	payload["candidate_key"] = "local:legacy-content-derived-key"
	store._write(path, payload)

	second = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "候选人A"}, "raw_text": "updated"},
		evaluation=_evaluation(80),
		source=source,
		rubric=rubric,
	)

	latest = store.latest_by_candidate(job_key="java")
	assert len(latest) == 1
	assert next(iter(latest.values()))["id"] == second["id"]
