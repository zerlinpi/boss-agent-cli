import time

import pytest

from boss_agent_cli.web import tasks as tasks_module


def _wait_for_terminal(manager, task_id: str, timeout: float = 3.0) -> dict:
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		task = manager.get(task_id)
		if task["status"] in {"completed", "failed"}:
			return task
		time.sleep(0.01)
	raise AssertionError(f"task {task_id} did not reach a terminal state")


def test_task_controls_match_current_task_manager_contract(tmp_path) -> None:
	manager = tasks_module.TaskManager(
		storage_path=tmp_path / "web_tasks.db",
		max_workers=1,
		max_tasks=10,
	)
	try:
		assert hasattr(type(manager), "_trim_locked")
		assert hasattr(type(manager), "recent")
		assert hasattr(type(manager), "delete_for_job")

		def worker(progress):
			progress(50, "half")
			return {"job_key": "job-compat", "evaluation_ids": []}

		created = manager.submit(
			"screen-local",
			worker,
			metadata={"job_key": "job-compat"},
		)
		finished = _wait_for_terminal(manager, created["id"])

		assert finished["status"] == "completed"
		assert finished["progress"] == 100
		assert finished["result"]["job_key"] == "job-compat"
		assert manager.recent(limit=1)[0]["id"] == created["id"]
		assert manager.has_active_screening("job-compat") is False

		assert manager.delete_for_job("job-compat") == 1
		with pytest.raises(KeyError):
			manager.get(created["id"])
	finally:
		manager.close(wait=True)
