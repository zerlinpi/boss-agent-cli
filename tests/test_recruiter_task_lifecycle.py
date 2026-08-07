from __future__ import annotations

import sqlite3
import time
from threading import Event

import pytest

from boss_agent_cli.recruiter_ai import normalize_rubric, validate_evaluation
from boss_agent_cli.web import RecruiterWebController
from boss_agent_cli.web.controller import WebConsoleError
from boss_agent_cli.web.server import RecruiterWebApplication
from boss_agent_cli.web.tasks import TaskManager


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


def _wait_for_task(manager: TaskManager, task_id: str, status: str = "completed"):
	deadline = time.time() + 3
	current = None
	while time.time() < deadline:
		current = manager.get(task_id)
		if current and current["status"] == status:
			return current
		time.sleep(0.02)
	raise AssertionError(f"task {task_id} did not reach {status}: {current}")


def _candidate(controller: RecruiterWebController, job_key: str = "java"):
	rubric = normalize_rubric()
	controller.save_job({"job_key": job_key, "title": job_key, "jd_text": "Backend engineer"})
	return controller.store.save_evaluation(
		job_key=job_key,
		jd_text="Backend engineer",
		resume={"basic": {"name": "Alice"}},
		evaluation=_evaluation(rubric),
		rubric=rubric,
	)


def test_candidate_delete_scrubs_persisted_task_results(tmp_path):
	controller = RecruiterWebController(tmp_path)
	record = _candidate(controller)
	application = RecruiterWebApplication(controller, token="fixed")
	try:
		task = application.tasks.submit(
			"screen-local",
			lambda progress: {
				"job_key": "java",
				"evaluation_ids": [record["id"]],
				"skipped_ids": [record["id"]],
				"ranking": [{"evaluation_id": record["id"], "candidate_name": "Alice"}],
				"reply_drafts": [{"evaluation_id": record["id"], "draft": {"reply": "hello"}}],
			},
			metadata={"job_key": "java"},
		)
		_wait_for_task(application.tasks, task["id"])

		result = application.post(
			f"/api/candidates/{record['id']}/status",
			{"status": "__delete__", "note": ""},
		)
		assert result["task_records_scrubbed"] == 1
		cleaned = application.tasks.get(task["id"])
		assert cleaned is not None
		assert cleaned["result"]["evaluation_ids"] == []
		assert cleaned["result"]["skipped_ids"] == []
		assert cleaned["result"]["ranking"] == []
		assert cleaned["result"]["reply_drafts"] == []
	finally:
		application.tasks.close()

	reloaded = TaskManager(storage_path=tmp_path / "recruiter-ai" / "web_tasks.db")
	try:
		persisted = reloaded.get(task["id"])
		assert persisted is not None
		assert "Alice" not in str(persisted["result"])
		assert record["id"] not in str(persisted["result"])
	finally:
		reloaded.close()


def test_job_delete_removes_linked_task_history(tmp_path):
	controller = RecruiterWebController(tmp_path)
	_candidate(controller)
	application = RecruiterWebApplication(controller, token="fixed")
	try:
		task = application.tasks.submit(
			"screen-local",
			lambda progress: {"job_key": "java", "ranking": []},
			metadata={"job_key": "java"},
		)
		_wait_for_task(application.tasks, task["id"])
		result = application.post("/api/jobs", {"_delete": True, "job_key": "java"})
		assert result["task_records_deleted"] == 1
		assert application.tasks.get(task["id"]) is None
	finally:
		application.tasks.close()


def test_delete_is_blocked_while_linked_screening_is_running(tmp_path):
	controller = RecruiterWebController(tmp_path)
	record = _candidate(controller)
	application = RecruiterWebApplication(controller, token="fixed")
	release = Event()
	try:
		task = application.tasks.submit(
			"screen-local",
			lambda progress: (release.wait(2), {"job_key": "java"})[1],
			metadata={"job_key": "java"},
		)
		_wait_for_task(application.tasks, task["id"], status="running")
		with pytest.raises(WebConsoleError) as exc_info:
			application.post(
				f"/api/candidates/{record['id']}/status",
				{"status": "__delete__", "note": ""},
			)
		assert exc_info.value.code == "SCREENING_IN_PROGRESS"
		assert exc_info.value.status == 409
		assert controller.candidate_detail(record["id"])["id"] == record["id"]
	finally:
		release.set()
		application.tasks.close()


def test_corrupt_optional_task_json_does_not_prevent_web_startup(tmp_path):
	path = tmp_path / "web_tasks.db"
	manager = TaskManager(storage_path=path)
	manager.close()

	connection = sqlite3.connect(path)
	try:
		connection.execute(
			"""
			INSERT INTO web_tasks (
				id, kind, status, progress, message, created_at, updated_at,
				result_json, error_json, metadata_json
			) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			""",
			(
				"task_corrupt", "screen-local", "completed", 100, "done",
				"2026-08-07T00:00:00+00:00", "2026-08-07T00:00:01+00:00",
				"{broken", "{also-broken", "{metadata-broken",
			),
		)
		connection.commit()
	finally:
		connection.close()

	reloaded = TaskManager(storage_path=path)
	try:
		task = reloaded.get("task_corrupt")
		assert task is not None
		assert task["result"] is None
		assert task["error"] is None
		assert task["metadata"] == {}
	finally:
		reloaded.close()


def test_task_recent_handles_invalid_limits_without_crashing(tmp_path):
	manager = TaskManager(storage_path=tmp_path / "web_tasks.db")
	try:
		assert manager.recent(limit="invalid") == []  # type: ignore[arg-type]
		assert manager.recent(limit=-100) == []
	finally:
		manager.close()
