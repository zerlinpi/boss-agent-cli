from __future__ import annotations

import json
import time
from datetime import datetime

import pytest

from boss_agent_cli.recruiter_ai import normalize_rubric
from boss_agent_cli.web import RecruiterWebController, WebConsoleError, build_server
from boss_agent_cli.web import controller as controller_module
from boss_agent_cli.web.server import RecruiterWebApplication


def _job(controller: RecruiterWebController, job_key: str = "python") -> dict:
	return controller.save_job({
		"job_key": job_key,
		"title": "Python 后端",
		"jd_text": "负责 Python、FastAPI 和 PostgreSQL 服务开发，要求具备生产项目经验。",
	})


def _wait_task(application: RecruiterWebApplication, task_id: str) -> dict:
	deadline = time.time() + 2
	while time.time() < deadline:
		task = application.tasks.get(task_id)
		if task and task["status"] in {"completed", "failed"}:
			return task
		time.sleep(0.01)
	raise AssertionError(f"task did not finish: {task_id}")


def test_all_unchanged_local_screen_does_not_require_ai_configuration(tmp_path):
	controller = RecruiterWebController(tmp_path)
	job = _job(controller)
	resume = {"name": "Alice", "skills": ["Python", "FastAPI"], "raw_text": "5年 Python FastAPI 经验"}
	source = {"type": "web-upload", "filename": "alice.json", "format": "json"}
	controller.store.save_evaluation(
		job_key="python",
		jd_text=job["jd_text"],
		resume=resume,
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		source=source,
		rubric=normalize_rubric(job["rubric"]),
	)

	result = controller.screen_local({
		"job_key": "python",
		"documents": [{"name": "alice.json", "payload": resume}],
	})

	assert result["processed_count"] == 0
	assert result["skipped_unchanged_count"] == 1
	assert result["failed_count"] == 0


def test_analytics_accepts_legacy_naive_timestamp_and_ignores_non_finite_metrics(tmp_path):
	controller = RecruiterWebController(tmp_path)
	job = _job(controller)
	record = controller.store.save_evaluation(
		job_key="python",
		jd_text=job["jd_text"],
		resume={"name": "Alice"},
		evaluation={"total_score": 88, "recommendation": "strong_interview", "confidence": 0.9},
		source={"type": "test", "candidate_id": "alice"},
		rubric=normalize_rubric(job["rubric"]),
	)
	path = controller.store.evaluations_dir / f"{record['id']}.json"
	stored = json.loads(path.read_text(encoding="utf-8"))
	stored["created_at"] = datetime.now().replace(microsecond=0).isoformat()
	path.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")

	controller.store.save_evaluation(
		job_key="python",
		jd_text=job["jd_text"],
		resume={"name": "Legacy"},
		evaluation={"total_score": float("nan"), "recommendation": "manual_review", "confidence": float("inf")},
		source={"type": "test", "candidate_id": "legacy"},
		rubric=normalize_rubric(job["rubric"]),
	)

	analytics = controller.analytics("python")

	assert analytics["total"] == 2
	assert analytics["recent_7d"] == 2
	assert analytics["average_score"] == 88
	assert analytics["average_confidence"] == 0.9


def test_malformed_friend_id_is_ignored_instead_of_crashing_chat_batch():
	malformed = controller_module.extract_candidate_ref({
		"friendId": "encrypted-or-invalid",
		"geekCard": {"geekId": "g1", "securityId": "s1", "name": "Alice"},
	}, default_job_id="j1")
	valid = controller_module.extract_candidate_ref({
		"friendId": "123",
		"geekCard": {"geekId": "g2", "securityId": "s2", "name": "Bob"},
	}, default_job_id="j1")

	assert malformed["friend_id"] is None
	assert valid["friend_id"] == 123


def test_legacy_stored_friend_id_is_normalized_on_rank_and_detail(tmp_path):
	controller = RecruiterWebController(tmp_path)
	job = _job(controller)
	record = controller.store.save_evaluation(
		job_key="python",
		jd_text=job["jd_text"],
		resume={"name": "Alice"},
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		source={"type": "zhipin", "candidate_id": "alice", "friend_id": "bad-legacy-id"},
		rubric=normalize_rubric(job["rubric"]),
	)
	assert controller.store.rank(job_key="python", top=1)[0]["source"]["friend_id"] is None
	assert controller.candidate_detail(record["id"])["source"]["friend_id"] is None


def test_screen_boss_rejects_invalid_numeric_and_boolean_inputs_before_platform_access(tmp_path):
	controller = RecruiterWebController(tmp_path)
	_job(controller)
	base = {"job_key": "python", "job_id": "boss-1"}

	for field, value in (("pages", "many"), ("limit", 0), ("draft_top", 21), ("force", "sometimes")):
		payload = {**base, field: value}
		with pytest.raises(WebConsoleError) as caught:
			controller.screen_boss(payload)
		assert caught.value.code == "INVALID_PARAM"


def test_login_post_normalizes_string_boolean_before_task_submission(tmp_path):
	controller = RecruiterWebController(tmp_path)
	captured = {}

	def fake_login(*, timeout=180, cookie_source=None, force_cdp=False, progress=None):
		captured.update({"timeout": timeout, "cookie_source": cookie_source, "force_cdp": force_cdp})
		return dict(captured)

	controller.login = fake_login  # type: ignore[method-assign]
	application = RecruiterWebApplication(controller, token="fixed")
	try:
		task = application.post("/api/auth/login", {
			"timeout": "45",
			"cookie_source": "chrome",
			"force_cdp": "false",
		})
		completed = _wait_task(application, task["id"])
		assert completed["status"] == "completed"
		assert completed["result"]["timeout"] == 45
		assert completed["result"]["force_cdp"] is False
		assert captured["force_cdp"] is False
	finally:
		application.tasks.close()


def test_login_post_rejects_invalid_inputs_before_creating_task(tmp_path):
	application = RecruiterWebApplication(RecruiterWebController(tmp_path), token="fixed")
	try:
		for payload in (
			{"timeout": "later"},
			{"timeout": 10},
			{"force_cdp": "maybe"},
			{"cookie_source": ["chrome"]},
		):
			with pytest.raises(WebConsoleError) as caught:
				application.post("/api/auth/login", payload)
			assert caught.value.code == "INVALID_PARAM"
		assert application.tasks.recent(limit=20) == []
	finally:
		application.tasks.close()


def test_generate_reply_rejects_unknown_intent_and_oversized_conversation(tmp_path):
	controller = RecruiterWebController(tmp_path)

	with pytest.raises(WebConsoleError) as caught:
		controller.generate_reply({"evaluation_id": "eval_missing", "intent": "auto_hire"})
	assert caught.value.code == "INVALID_REPLY_INPUT"

	with pytest.raises(WebConsoleError) as caught:
		controller.generate_reply({
			"evaluation_id": "eval_missing",
			"intent": "auto",
			"conversation": "x" * 200_001,
		})
	assert caught.value.code == "INVALID_REPLY_INPUT"


def test_replies_limit_is_bounded_and_invalid_limit_falls_back(tmp_path):
	controller = RecruiterWebController(tmp_path)
	assert controller.replies(limit=-1) == []
	assert controller.replies(limit="invalid") == []  # type: ignore[arg-type]


def test_native_web_rejects_invalid_explicit_ports(tmp_path):
	controller = RecruiterWebController(tmp_path)
	for port in (-1, 65536, True):
		with pytest.raises(ValueError, match="端口"):
			build_server(controller, port=port)  # type: ignore[arg-type]


def test_native_web_still_allows_ephemeral_test_port(tmp_path):
	server, application = build_server(RecruiterWebController(tmp_path), port=0)
	try:
		assert server.server_port > 0
	finally:
		application.tasks.close()
		server.server_close()
