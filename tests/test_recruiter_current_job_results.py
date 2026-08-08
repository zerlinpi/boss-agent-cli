from boss_agent_cli.recruiter_ai import normalize_rubric
from boss_agent_cli.web import RecruiterWebController


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


def test_web_current_results_exclude_stale_job_evaluations(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	rubric = normalize_rubric()
	controller.store.save_job(job_key="java", jd_text="旧 JD", rubric=rubric)
	for geek_id, name, score in (("g1", "A", 80), ("g2", "B", 70)):
		controller.store.save_evaluation(
			job_key="java",
			jd_text="旧 JD",
			resume={"basic": {"name": name}},
			evaluation=_evaluation(score),
			source={"type": "zhipin", "geek_id": geek_id},
			rubric=rubric,
		)

	controller.store.save_job(job_key="java", jd_text="新 JD，新增 Kafka 职责", rubric=rubric)
	result = controller.candidates("java", top=20)

	assert result["items"] == []
	assert result["stale_count"] == 2
	assert result["report"]["total_candidates"] == 0
	assert result["report"]["stale_count"] == 2
	assert result["analytics"]["total"] == 0
	assert result["analytics"]["stale_count"] == 2
	csv = controller.export_candidates("java")["content"]
	assert "score 80" not in csv
	assert "score 70" not in csv


def test_web_current_results_restore_only_re_evaluated_candidates(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	rubric = normalize_rubric()
	controller.store.save_job(job_key="java", jd_text="旧 JD", rubric=rubric)
	for geek_id, name, score in (("g1", "A", 80), ("g2", "B", 70)):
		controller.store.save_evaluation(
			job_key="java", jd_text="旧 JD", resume={"basic": {"name": name}},
			evaluation=_evaluation(score), source={"type": "zhipin", "geek_id": geek_id}, rubric=rubric,
		)
	controller.store.save_job(job_key="java", jd_text="新 JD", rubric=rubric)
	controller.store.save_evaluation(
		job_key="java", jd_text="新 JD", resume={"basic": {"name": "A"}},
		evaluation=_evaluation(90), source={"type": "zhipin", "geek_id": "g1"}, rubric=rubric,
	)

	result = controller.candidates("java", top=20)
	assert [item["candidate_name"] for item in result["items"]] == ["A"]
	assert result["items"][0]["total_score"] == 90
	assert result["stale_count"] == 1
	assert result["report"]["total_candidates"] == 1
