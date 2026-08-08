import pytest

from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric
from boss_agent_cli.web import RecruiterWebController, WebConsoleError
from boss_agent_cli.web.server import RecruiterWebApplication


def test_candidates_api_maps_corrupt_evaluation_to_integrity_error(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	store: RecruiterAIStore = controller.store
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="JD", rubric=rubric)
	record = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "A"}},
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		source={"type": "zhipin", "geek_id": "g1"},
		rubric=rubric,
	)
	(store.evaluations_dir / f"{record['id']}.json").write_text("{not-json", encoding="utf-8")
	application = RecruiterWebApplication(controller, token="fixed")
	try:
		with pytest.raises(WebConsoleError) as exc_info:
			application.get("/api/candidates", {"job_key": ["java"], "top": ["20"]})
		assert exc_info.value.code == "DATA_INTEGRITY_ERROR"
		assert exc_info.value.status == 409
		assert "评估文件损坏" in str(exc_info.value)
	finally:
		application.tasks.close()
