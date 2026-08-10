import time

import pytest

from boss_agent_cli.web.tasks import TaskManager


def _wait_terminal(manager: TaskManager, task_id: str) -> dict:
	deadline = time.time() + 3
	while time.time() < deadline:
		task = manager.get(task_id)
		if task["status"] in {"completed", "failed"}:
			return task
		time.sleep(0.01)
	raise AssertionError("task did not finish")


def test_non_serializable_task_result_fails_cleanly(tmp_path) -> None:
	manager = TaskManager(storage_path=tmp_path / "tasks.db")
	try:
		task = manager.submit("unsafe-result", lambda progress: {"items": {"not-json"}})
		finished = _wait_terminal(manager, task["id"])
		assert finished["status"] == "failed"
		assert "无法持久化" in finished["message"]
		assert finished["result"] is None
	finally:
		manager.close()


def test_non_object_task_result_fails_cleanly(tmp_path) -> None:
	manager = TaskManager(storage_path=tmp_path / "tasks.db")
	try:
		task = manager.submit("unsafe-shape", lambda progress: ["not", "an", "object"])
		finished = _wait_terminal(manager, task["id"])
		assert finished["status"] == "failed"
		assert "JSON 对象" in finished["message"]
	finally:
		manager.close()


def test_non_serializable_task_metadata_is_rejected_before_queueing(tmp_path) -> None:
	manager = TaskManager(storage_path=tmp_path / "tasks.db")
	try:
		with pytest.raises(TypeError, match="metadata"):
			manager.submit("unsafe-metadata", lambda progress: {}, metadata={"bad": {1, 2}})
		assert manager.list() == []
	finally:
		manager.close()
