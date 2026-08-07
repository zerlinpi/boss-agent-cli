from __future__ import annotations

import time
from pathlib import Path
from threading import Event

from boss_agent_cli.web import RecruiterWebController
from boss_agent_cli.web.server import RecruiterWebApplication
from boss_agent_cli.web.tasks import TaskManager


def _wait_for(manager: TaskManager, task_id: str, status: str, timeout: float = 3.0):
	deadline = time.time() + timeout
	last = None
	while time.time() < deadline:
		last = manager.get(task_id)
		if last and last["status"] == status:
			return last
		time.sleep(0.02)
	raise AssertionError(f"task {task_id} did not reach {status}: {last}")


def test_queued_task_cancel_prevents_function_execution(tmp_path: Path) -> None:
	manager = TaskManager(storage_path=tmp_path / "tasks.db", max_workers=1)
	blocker = Event()
	started = Event()
	executed = Event()
	try:
		first = manager.submit(
			"blocker",
			lambda progress: (started.set(), blocker.wait(2), {"ok": True})[2],
		)
		assert started.wait(1)
		second = manager.submit(
			"queued",
			lambda progress: (executed.set(), {"ok": True})[1],
		)

		cancelled = manager.cancel(second["id"])
		assert cancelled is not None
		assert cancelled["status"] == "failed"
		assert cancelled["error"]["code"] == "TASK_CANCELLED"

		blocker.set()
		_wait_for(manager, first["id"], "completed")
		time.sleep(0.05)
		assert executed.is_set() is False
	finally:
		blocker.set()
		manager.close()


def test_running_task_cancel_never_becomes_completed(tmp_path: Path) -> None:
	manager = TaskManager(storage_path=tmp_path / "tasks.db", max_workers=1)
	started = Event()
	release = Event()
	try:
		def work(progress):
			started.set()
			release.wait(2)
			progress(80, "almost done")
			return {"ok": True}

		task = manager.submit("running", work)
		assert started.wait(1)
		cancelled = manager.cancel(task["id"])
		assert cancelled is not None
		assert cancelled["error"]["code"] == "TASK_CANCELLED"
		release.set()
		time.sleep(0.1)

		final = manager.get(task["id"])
		assert final is not None
		assert final["status"] == "failed"
		assert final["error"]["code"] == "TASK_CANCELLED"
		assert final["result"] is None
	finally:
		release.set()
		manager.close()


def test_web_cancel_endpoint_and_asset_are_installed(tmp_path: Path) -> None:
	controller = RecruiterWebController(tmp_path)
	application = RecruiterWebApplication(controller, token="fixed")
	started = Event()
	release = Event()
	try:
		task = application.tasks.submit(
			"running",
			lambda progress: (started.set(), release.wait(2), {"ok": True})[2],
		)
		assert started.wait(1)

		result = application.post(f"/api/tasks/{task['id']}/cancel", {})
		assert result["status"] == "failed"
		assert result["error"]["code"] == "TASK_CANCELLED"

		app_js, content_type = application.asset("app.js")
		assert content_type.startswith("text/javascript")
		assert b"task-cancel-button" in app_js
	finally:
		release.set()
		application.tasks.close()
