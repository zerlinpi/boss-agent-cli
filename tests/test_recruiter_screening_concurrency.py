from __future__ import annotations

from threading import Event

import pytest

from boss_agent_cli.web import RecruiterWebController
from boss_agent_cli.web.controller import WebConsoleError
from boss_agent_cli.web.server import RecruiterWebApplication


def test_same_job_screening_submission_is_rejected_while_active(tmp_path):
	application = RecruiterWebApplication(RecruiterWebController(tmp_path), token="fixed")
	release = Event()
	try:
		application.tasks.submit(
			"screen-local",
			lambda progress: (release.wait(2), {"job_key": "java"})[1],
			metadata={"job_key": "java"},
		)
		with pytest.raises(WebConsoleError) as exc_info:
			application.post(
				"/api/screen/local",
				{"job_key": "java", "documents": [{"name": "resume.txt"}]},
			)
		assert exc_info.value.code == "SCREENING_IN_PROGRESS"
		assert exc_info.value.status == 409
	finally:
		release.set()
		application.tasks.close()


def test_different_job_screening_submission_is_not_blocked_by_guard(tmp_path):
	application = RecruiterWebApplication(RecruiterWebController(tmp_path), token="fixed")
	release = Event()
	try:
		application.tasks.submit(
			"screen-local",
			lambda progress: (release.wait(2), {"job_key": "java"})[1],
			metadata={"job_key": "java"},
		)
		task = application.post(
			"/api/screen/local",
			{"job_key": "python", "documents": [{"name": "resume.txt"}]},
		)
		assert task["kind"] == "screen-local"
		assert task["metadata"]["job_key"] == "python"
	finally:
		release.set()
		application.tasks.close()
