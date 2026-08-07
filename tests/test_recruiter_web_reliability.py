from __future__ import annotations

import json
from datetime import datetime

import pytest

from boss_agent_cli.recruiter_ai import normalize_rubric
from boss_agent_cli.web import RecruiterWebController, build_server
from boss_agent_cli.web import controller as controller_module


def _job(controller: RecruiterWebController, job_key: str = "python") -> dict:
	return controller.save_job({
		"job_key": job_key,
		"title": "Python 后端",
		"jd_text": "负责 Python、FastAPI 和 PostgreSQL 服务开发，要求具备生产项目经验。",
	})


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


def test_analytics_accepts_legacy_naive_timestamp(tmp_path):
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

	analytics = controller.analytics("python")

	assert analytics["total"] == 1
	assert analytics["recent_7d"] == 1
	assert analytics["average_score"] == 88


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
