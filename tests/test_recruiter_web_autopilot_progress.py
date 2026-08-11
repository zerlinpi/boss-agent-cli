import pytest

from boss_agent_cli.web.autopilot_progress import wrap_autopilot_dependencies


class FakePlatform:
	def list_jobs(self):
		return {"code": 0}

	def view_geek(self, geek_id, job_id, security_id=None):
		return {"geek_id": geek_id, "job_id": job_id, "security_id": security_id}

	def is_success(self, response):
		return True


class FakeService:
	def chat(self, messages, **kwargs):
		return "ok"


def test_autopilot_progress_wraps_network_and_ai_steps():
	updates = []
	platform, service = wrap_autopilot_dependencies(
		FakePlatform(),
		FakeService(),
		lambda percent, message: updates.append((percent, message)),
	)
	assert platform.list_jobs() == {"code": 0}
	assert platform.view_geek("g", "j", security_id="s")["geek_id"] == "g"
	assert service.chat([{"role": "user", "content": "test"}]) == "ok"
	assert len(updates) == 3
	assert [item[0] for item in updates] == sorted(item[0] for item in updates)
	assert any("AI" in message for _, message in updates)


def test_autopilot_progress_propagates_cancellation_before_request():
	class Cancelled(RuntimeError):
		pass

	def cancel(_percent, _message):
		raise Cancelled("cancelled")

	platform, _service = wrap_autopilot_dependencies(FakePlatform(), FakeService(), cancel)
	with pytest.raises(Cancelled):
		platform.list_jobs()
