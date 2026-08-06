from __future__ import annotations

import time

import pytest

from boss_agent_cli.web.controller import RecruiterWebController
from boss_agent_cli.web.server import RecruiterWebApplication, build_server
from boss_agent_cli.web.tasks import TaskManager


def test_controller_saves_job_and_mode(tmp_path):
	controller = RecruiterWebController(tmp_path)
	job = controller.save_job({
		"job_key": "java-backend",
		"title": "Java 后端",
		"boss_job_id": "boss-job-1",
		"jd_text": "需要 Java 和 Spring Boot 经验",
	})
	assert job["job_key"] == "java-backend"
	assert controller.list_jobs()[0]["boss_job_id"] == "boss-job-1"
	assert controller.set_operating_mode("research") == {"operating_mode": "research"}
	assert controller.bootstrap()["operating_mode"] == "research"


def test_controller_rejects_invalid_job(tmp_path):
	controller = RecruiterWebController(tmp_path)
	with pytest.raises(Exception, match="岗位标识和 JD"):
		controller.save_job({"job_key": "", "jd_text": ""})


def test_task_manager_completes():
	manager = TaskManager(max_workers=1)
	try:
		task = manager.submit("demo", lambda progress: (progress(80, "almost"), {"done": True})[1])
		deadline = time.time() + 3
		current = None
		while time.time() < deadline:
			current = manager.get(task["id"])
			if current and current["status"] == "completed":
				break
			time.sleep(0.02)
		assert current is not None
		assert current["status"] == "completed"
		assert current["result"] == {"done": True}
	finally:
		manager.close()


def test_application_replaces_asset_token(tmp_path):
	application = RecruiterWebApplication(RecruiterWebController(tmp_path), token="fixed-token")
	try:
		content, content_type = application.asset("app.js")
		assert b"fixed-token" in content
		assert b"__BOSS_WEB_TOKEN__" not in content
		assert "javascript" in content_type
	finally:
		application.tasks.close()


def test_server_rejects_remote_bind(tmp_path):
	with pytest.raises(ValueError, match="回环地址"):
		build_server(RecruiterWebController(tmp_path), host="0.0.0.0", port=0)


def test_server_can_bind_ephemeral_loopback_port(tmp_path):
	server, application = build_server(RecruiterWebController(tmp_path), port=0)
	try:
		assert server.server_port > 0
	finally:
		application.tasks.close()
		server.server_close()
