from boss_agent_cli.recruiter_ai import normalize_rubric, validate_evaluation
from boss_agent_cli.web import RecruiterWebController
from boss_agent_cli.web.server import RecruiterWebApplication


def _evaluation(rubric):
	return validate_evaluation({
		"confidence": 0.8,
		"hard_requirements": [],
		"dimensions": [
			{
				"name": item["name"], "score": 1, "max_score": item["max_score"],
				"reason": "evidence", "evidence": ["evidence"],
			}
			for item in rubric["dimensions"]
		],
		"strengths": [], "concerns": [], "next_questions": [], "summary": "",
	}, rubric)


def test_controller_lifecycle_deletes_candidate_and_job(tmp_path):
	controller = RecruiterWebController(tmp_path)
	rubric = normalize_rubric()
	controller.save_job({"job_key": "java", "title": "Java", "jd_text": "Java backend engineer"})
	record = controller.store.save_evaluation(
		job_key="java", jd_text="JD", resume={"basic": {"name": "Alice"}},
		evaluation=_evaluation(rubric), rubric=rubric,
	)
	controller.store.save_reply(
		evaluation_id=record["id"], intent="clarify", conversation="hello", draft={"reply": "draft"},
	)

	deleted = controller.mark_candidate(record["id"], "__delete__")
	assert deleted["evaluation_count"] == 1
	assert deleted["reply_count"] == 1

	job_deleted = controller.save_job({"_delete": True, "job_key": "java"})
	assert job_deleted["job_key"] == "java"
	assert controller.list_jobs() == []


def test_lifecycle_assets_are_appended(tmp_path):
	application = RecruiterWebApplication(RecruiterWebController(tmp_path), token="fixed")
	try:
		javascript, _ = application.asset("app.js")
		styles, _ = application.asset("styles.css")
		assert b"deleteCandidateLocal" in javascript
		assert b"danger-zone" in styles
	finally:
		application.tasks.close()
