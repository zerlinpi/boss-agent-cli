from boss_agent_cli.recruiter_ai import normalize_rubric
from boss_agent_cli.web import RecruiterWebController


def _save_candidate(controller: RecruiterWebController, name: str, index: int):
	rubric = normalize_rubric()
	return controller.store.save_evaluation(
		job_key="java",
		jd_text="Java JD",
		resume={"basic": {"name": name}, "work_experience": [{"company": f"Company {index}"}]},
		evaluation={"total_score": 80 - index, "recommendation": "interview", "confidence": 0.8},
		source={"type": "local-upload", "filename": f"resume-{index}.json"},
		rubric=rubric,
	)


def test_candidate_collection_reports_when_items_are_truncated(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	rubric = normalize_rubric()
	controller.store.save_job(job_key="java", jd_text="Java JD", rubric=rubric, metadata={"title": "Java"})
	for index, name in enumerate(("张三", "李四", "王五"), 1):
		_save_candidate(controller, name, index)

	result = controller.candidates("java", top=2)
	assert result["returned_count"] == 2
	assert result["total_count"] == 3
	assert result["truncated"] is True
	assert result["requested_top"] == 2
	assert result["report"]["total_candidates"] == 3


def test_candidate_collection_reports_complete_result_when_below_limit(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	rubric = normalize_rubric()
	controller.store.save_job(job_key="java", jd_text="Java JD", rubric=rubric, metadata={"title": "Java"})
	_save_candidate(controller, "张三", 1)

	result = controller.candidates("java", top=500)
	assert result["returned_count"] == 1
	assert result["total_count"] == 1
	assert result["truncated"] is False
