import pytest

from boss_agent_cli.web import RecruiterWebController, WebConsoleError
from boss_agent_cli.web.server import RecruiterWebApplication


def _application(tmp_path):
	controller = RecruiterWebController(tmp_path)
	controller.save_job({"job_key": "java", "title": "Java", "jd_text": "Java backend JD"})
	return RecruiterWebApplication(controller, token="fixed")


def test_string_false_cannot_trigger_job_deletion(tmp_path) -> None:
	application = _application(tmp_path)
	try:
		with pytest.raises(WebConsoleError) as caught:
			application.post("/api/jobs", {"_delete": "false", "job_key": "java"})
		assert caught.value.code == "INVALID_PARAM"
		assert application.controller.get_job("java")["job_key"] == "java"
	finally:
		application.tasks.close()


def test_job_delete_requires_literal_boolean_true(tmp_path) -> None:
	application = _application(tmp_path)
	try:
		result = application.post("/api/jobs", {"_delete": True, "job_key": "java"})
		assert result["job_key"] == "java"
		with pytest.raises(WebConsoleError):
			application.controller.get_job("java")
	finally:
		application.tasks.close()


def test_bulk_status_rejects_structured_ids_and_deduplicates_strings(tmp_path, monkeypatch) -> None:
	application = _application(tmp_path)
	captured = {}

	def bulk(payload):
		captured.update(payload)
		return {"updated_ids": payload["evaluation_ids"], "failed": [], "status": payload["status"]}

	monkeypatch.setattr(application.controller, "bulk_mark_candidates", bulk)
	try:
		with pytest.raises(WebConsoleError) as caught:
			application.post("/api/candidates/bulk-status", {
				"evaluation_ids": [{"id": "eval_1"}], "status": "interview", "note": "",
			})
		assert caught.value.code == "INVALID_PARAM"

		result = application.post("/api/candidates/bulk-status", {
			"evaluation_ids": ["eval_1", "eval_1", "eval_2"],
			"status": "interview",
			"note": "人工确认",
		})
		assert result["updated_ids"] == ["eval_1", "eval_2"]
		assert captured["evaluation_ids"] == ["eval_1", "eval_2"]
	finally:
		application.tasks.close()


def test_candidate_status_rejects_structured_note_before_controller_call(tmp_path, monkeypatch) -> None:
	application = _application(tmp_path)
	called = False

	def mark(*args, **kwargs):
		nonlocal called
		called = True
		return {}

	monkeypatch.setattr(application.controller, "mark_candidate", mark)
	try:
		with pytest.raises(WebConsoleError) as caught:
			application.post("/api/candidates/eval_1/status", {
				"status": "interview", "note": {"text": "not allowed"},
			})
		assert caught.value.code == "INVALID_PARAM"
		assert called is False
	finally:
		application.tasks.close()


@pytest.mark.parametrize(
	("path", "payload"),
	[
		("/api/jobs/analyze", {"jd_text": ["invalid"]}),
		("/api/screen/local", {"job_key": "java", "documents": ["not-an-object"]}),
		("/api/screen/local", {"job_key": "java", "documents": [{}], "force": "false"}),
		("/api/screen/boss", {"job_key": "java", "job_id": "job-1", "pages": 1.5}),
		("/api/screen/boss", {"job_key": "java", "job_id": {"id": "job-1"}}),
	],
)
def test_malformed_async_jobs_are_rejected_before_task_submission(tmp_path, monkeypatch, path, payload) -> None:
	application = _application(tmp_path)
	submitted = False

	def submit(*args, **kwargs):
		nonlocal submitted
		submitted = True
		return {}

	monkeypatch.setattr(application.tasks, "submit", submit)
	try:
		with pytest.raises(WebConsoleError):
			application.post(path, payload)
		assert submitted is False
	finally:
		application.tasks.close()
