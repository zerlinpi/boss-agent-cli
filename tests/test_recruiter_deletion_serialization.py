from threading import Event, Thread

from boss_agent_cli.web import RecruiterWebController
from boss_agent_cli.web import lifecycle as lifecycle_module
from boss_agent_cli.web.server import RecruiterWebApplication


def test_job_delete_waits_for_screen_submission_lock(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	application = RecruiterWebApplication(controller, token="fixed")
	entered_delete = Event()
	finished = Event()
	error: list[BaseException] = []

	def fake_save_job(payload):
		entered_delete.set()
		return {"job_key": payload["job_key"], "evaluation_count": 0, "reply_count": 0}

	controller.save_job = fake_save_job  # type: ignore[method-assign]

	def run_delete() -> None:
		try:
			application.post("/api/jobs", {"_delete": True, "job_key": "java"})
		except BaseException as exc:  # pragma: no cover - assertion below reports the worker failure
			error.append(exc)
		finally:
			finished.set()

	lock = lifecycle_module._SCREEN_SUBMIT_LOCK
	lock.acquire()
	thread = Thread(target=run_delete, daemon=True)
	try:
		thread.start()
		assert not entered_delete.wait(0.1)
		assert not finished.is_set()
	finally:
		lock.release()

	try:
		assert entered_delete.wait(1.0)
		assert finished.wait(1.0)
		thread.join(timeout=1.0)
		assert not thread.is_alive()
		assert error == []
	finally:
		application.tasks.close()
