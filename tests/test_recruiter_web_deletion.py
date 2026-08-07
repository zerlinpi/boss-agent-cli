from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric, validate_evaluation
from boss_agent_cli.web.deletion import delete_candidate_data, delete_job_data


def _evaluation(rubric):
	return validate_evaluation({
		"confidence": 0.8,
		"hard_requirements": [],
		"dimensions": [
			{
				"name": item["name"],
				"score": 1,
				"max_score": item["max_score"],
				"reason": "evidence",
				"evidence": ["evidence"],
			}
			for item in rubric["dimensions"]
		],
		"strengths": [],
		"concerns": [],
		"next_questions": [],
		"summary": "",
	}, rubric)


def test_delete_candidate_removes_all_versions_and_replies(tmp_path):
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	first = store.save_evaluation(
		job_key="java", jd_text="JD", resume={"basic": {"name": "Alice"}},
		evaluation=_evaluation(rubric), source={"type": "zhipin", "friend_id": 10}, rubric=rubric,
	)
	second = store.save_evaluation(
		job_key="java", jd_text="JD", resume={"basic": {"name": "Alice"}, "skills": ["Java"]},
		evaluation=_evaluation(rubric), source={"type": "zhipin", "friend_id": 10}, rubric=rubric,
	)
	store.save_reply(evaluation_id=first["id"], intent="clarify", conversation="hello", draft={"reply": "draft"})
	store.save_reply(evaluation_id=second["id"], intent="clarify", conversation="hello", draft={"reply": "draft"})

	result = delete_candidate_data(store, second["id"])

	assert result["evaluation_count"] == 2
	assert result["reply_count"] == 2
	assert store.list_evaluations(job_key="java") == []
	assert list(store.replies_dir.glob("reply_*.json")) == []


def test_delete_job_removes_only_linked_data(tmp_path):
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="Java", rubric=rubric)
	store.save_job(job_key="python", jd_text="Python", rubric=rubric)
	java = store.save_evaluation(
		job_key="java", jd_text="Java", resume={"basic": {"name": "Alice"}},
		evaluation=_evaluation(rubric), rubric=rubric,
	)
	python = store.save_evaluation(
		job_key="python", jd_text="Python", resume={"basic": {"name": "Bob"}},
		evaluation=_evaluation(rubric), rubric=rubric,
	)
	store.save_reply(evaluation_id=java["id"], intent="clarify", conversation="hello", draft={"reply": "draft"})
	store.save_reply(evaluation_id=python["id"], intent="clarify", conversation="hello", draft={"reply": "draft"})

	result = delete_job_data(store, "java")

	assert result["evaluation_count"] == 1
	assert result["reply_count"] == 1
	assert [item["job_key"] for item in store.list_jobs()] == ["python"]
	assert [item["job_key"] for item in store.list_evaluations()] == ["python"]
	assert len(list(store.replies_dir.glob("reply_*.json"))) == 1
