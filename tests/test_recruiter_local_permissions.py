import os
import stat

import pytest

from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric
from boss_agent_cli.web.audit import AuditLog
from boss_agent_cli.web.tasks import TaskManager

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not portable to Windows")


def _mode(path) -> int:
	return stat.S_IMODE(path.stat().st_mode)


def test_recruiter_store_uses_private_directories_and_files(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	job = store.save_job(job_key="java", jd_text="Java JD", rubric=normalize_rubric())
	evaluation = store.save_evaluation(
		job_key="java",
		jd_text="Java JD",
		resume={"basic": {"name": "张三"}},
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		rubric=job["rubric"],
	)
	reply = store.save_reply(
		evaluation_id=evaluation["id"],
		intent="acknowledge",
		conversation="收到",
		draft={"reply": "已收到"},
	)

	assert _mode(store.root) == 0o700
	for directory in (store.jobs_dir, store.evaluations_dir, store.replies_dir):
		assert _mode(directory) == 0o700
	assert _mode(store.jobs_dir / "java.json") == 0o600
	assert _mode(store.evaluations_dir / f"{evaluation['id']}.json") == 0o600
	assert _mode(store.replies_dir / f"{reply['id']}.json") == 0o600


def test_task_database_and_audit_log_are_private(tmp_path) -> None:
	storage = tmp_path / "private" / "web_tasks.db"
	manager = TaskManager(storage_path=storage)
	try:
		assert _mode(storage.parent) == 0o700
		assert _mode(storage) == 0o600
	finally:
		manager.close()

	audit = AuditLog(tmp_path)
	audit.append("test.action", entity_type="test", summary="test")
	assert _mode(audit.path.parent) == 0o700
	assert _mode(audit.path) == 0o600
