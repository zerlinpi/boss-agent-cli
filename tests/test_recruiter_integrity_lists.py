import pytest

from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric
from boss_agent_cli.web import RecruiterWebController, WebConsoleError
from boss_agent_cli.web.server import RecruiterWebApplication


def test_jobs_api_surfaces_corrupt_job_file(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	controller.store.save_job(job_key="java", jd_text="JD", rubric=normalize_rubric())
	(controller.store.jobs_dir / "broken.json").write_text("{not-json", encoding="utf-8")
	application = RecruiterWebApplication(controller, token="fixed")
	try:
		with pytest.raises(WebConsoleError) as exc_info:
			application.get("/api/jobs", {})
		assert exc_info.value.code == "DATA_INTEGRITY_ERROR"
		assert exc_info.value.status == 409
		assert "岗位配置文件损坏" in str(exc_info.value)
	finally:
		application.tasks.close()


def test_replies_api_surfaces_corrupt_reply_file(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	store: RecruiterAIStore = controller.store
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="JD", rubric=rubric)
	record = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "A"}},
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		source={"type": "local"},
		rubric=rubric,
	)
	store.save_reply(
		evaluation_id=record["id"],
		intent="acknowledge",
		conversation="",
		draft={"reply": "已收到。"},
	)
	(store.replies_dir / "reply_broken.json").write_text("{not-json", encoding="utf-8")
	application = RecruiterWebApplication(controller, token="fixed")
	try:
		with pytest.raises(WebConsoleError) as exc_info:
			application.get("/api/replies", {})
		assert exc_info.value.code == "DATA_INTEGRITY_ERROR"
		assert exc_info.value.status == 409
		assert "回复草稿文件损坏" in str(exc_info.value)
	finally:
		application.tasks.close()
