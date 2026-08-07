from __future__ import annotations

import base64
import sqlite3
import time
from io import BytesIO
from zipfile import ZipFile

import pytest

from boss_agent_cli.web.audit import AuditLog
from boss_agent_cli.web.controller import RecruiterWebController
from boss_agent_cli.web.documents import DocumentParseError, parse_uploaded_document
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
	bootstrap = controller.bootstrap()
	assert bootstrap["operating_mode"] == "research"
	assert bootstrap["candidate_statuses"] == ["new", "shortlisted", "interview", "hold", "hired", "rejected"]
	assert ".pdf" in bootstrap["supported_upload_extensions"]


def test_controller_rejects_invalid_job(tmp_path):
	controller = RecruiterWebController(tmp_path)
	with pytest.raises(Exception, match="岗位标识和 JD"):
		controller.save_job({"job_key": "", "jd_text": ""})


def test_controller_bulk_status_export_and_audit(tmp_path):
	controller = RecruiterWebController(tmp_path)
	controller.save_job({"job_key": "python", "title": "Python", "jd_text": "Python backend engineer"})
	record = controller.store.save_evaluation(
		job_key="python",
		jd_text="Python backend engineer",
		resume={"name": "Alice", "skills": ["Python"]},
		evaluation={
			"total_score": 88,
			"recommendation": "strong_interview",
			"confidence": 0.9,
			"strengths": ["Python"],
			"concerns": [],
			"next_questions": [],
			"summary": "匹配",
		},
		source={"type": "test"},
	)
	result = controller.bulk_mark_candidates({
		"evaluation_ids": [record["id"]],
		"status": "shortlisted",
		"note": "人工确认",
	})
	assert result["updated_ids"] == [record["id"]]
	assert controller.candidate_detail(record["id"])["status"] == "shortlisted"
	export = controller.export_candidates("python")
	assert export["filename"] == "python-candidates.csv"
	assert "Alice" in export["content"]
	assert controller.audit_events(limit=10)[0]["action"] == "candidate.status.bulk_updated"


def test_task_manager_completes_and_persists(tmp_path):
	path = tmp_path / "tasks.db"
	manager = TaskManager(storage_path=path, max_workers=1)
	try:
		task = manager.submit(
			"demo",
			lambda progress: (progress(80, "almost"), {"done": True})[1],
			metadata={"title": "Demo"},
		)
		deadline = time.time() + 3
		current = None
		while time.time() < deadline:
			current = manager.get(task["id"])
			if current and current["status"] == "completed":
				break
			time.sleep(0.02)
		assert current is not None
		assert current["result"] == {"done": True}
	finally:
		manager.close()

	reloaded = TaskManager(storage_path=path, max_workers=1)
	try:
		item = reloaded.get(task["id"])
		assert item is not None
		assert item["status"] == "completed"
		assert item["metadata"]["title"] == "Demo"
	finally:
		reloaded.close()


def test_task_manager_marks_interrupted_tasks_failed(tmp_path):
	path = tmp_path / "tasks.db"
	manager = TaskManager(storage_path=path)
	manager.close()
	with sqlite3.connect(path) as db:
		db.execute(
			"INSERT INTO web_tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
			("task_old", "screen-local", "running", 40, "running", "2026-01-01", "2026-01-01", None, None, "{}"),
		)
	reloaded = TaskManager(storage_path=path)
	try:
		item = reloaded.get("task_old")
		assert item is not None
		assert item["status"] == "failed"
		assert item["error"]["code"] == "TASK_INTERRUPTED"
	finally:
		reloaded.close()


def test_parse_text_and_json_documents():
	text = "张三\n五年 Python 与 FastAPI 经验\n负责订单系统和 PostgreSQL 数据库"
	resume, source = parse_uploaded_document({
		"name": "resume.txt",
		"content_base64": base64.b64encode(text.encode()).decode(),
	})
	assert "FastAPI" in resume["raw_text"]
	assert source["format"] == "txt"

	resume, source = parse_uploaded_document({"name": "resume.json", "payload": {"name": "Alice"}})
	assert resume["name"] == "Alice"
	assert source["format"] == "json"


def test_parse_docx_document():
	buffer = BytesIO()
	with ZipFile(buffer, "w") as archive:
		archive.writestr(
			"word/document.xml",
			'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
			'<w:body><w:p><w:r><w:t>四年 Java Spring Boot 经验</w:t></w:r></w:p></w:body></w:document>',
		)
	resume, source = parse_uploaded_document({
		"name": "resume.docx",
		"content_base64": base64.b64encode(buffer.getvalue()).decode(),
	})
	assert "Spring Boot" in resume["raw_text"]
	assert source["format"] == "docx"


def test_parse_document_rejects_unsupported_type():
	with pytest.raises(DocumentParseError, match="不支持"):
		parse_uploaded_document({
			"name": "resume.exe",
			"content_base64": base64.b64encode(b"content").decode(),
		})


def test_audit_log_is_append_only(tmp_path):
	audit = AuditLog(tmp_path)
	audit.append("job.saved", entity_type="job", entity_id="java", summary="保存岗位")
	audit.append("candidate.updated", entity_type="candidate", entity_id="1", summary="更新候选人")
	items = audit.list(limit=10)
	assert [item["action"] for item in items] == ["candidate.updated", "job.saved"]


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
