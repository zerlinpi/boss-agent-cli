import json
from pathlib import Path

from boss_agent_cli.commands.recruiter.ai_autopilot_job_profile import prepare_autopilot_job_profiles
from boss_agent_cli.recruiter_ai import RecruiterAIStore


class FakePlatform:
	def __init__(self) -> None:
		self.jd = "负责 Python 后端服务开发、测试与稳定性优化。"
		self.detail_calls = 0

	def is_success(self, response):
		return response.get("code") == 0

	def unwrap_data(self, response):
		return response.get("zpData")

	def parse_error(self, response):
		return "ERROR", str(response.get("message") or "failed")

	def list_jobs(self):
		return {"code": 0, "zpData": {"jobList": [{"encryptJobId": "job-1", "jobName": "Backend"}]}}

	def job_detail(self, enc_job_id):
		self.detail_calls += 1
		return {
			"code": 0,
			"zpData": {
				"job": {
					"encryptJobId": enc_job_id,
					"jobName": "Backend",
					"jobDescription": self.jd,
				}
			},
		}


class FakeService:
	def __init__(self, *, protected=False) -> None:
		self.calls = 0
		self.protected = protected

	def chat(self, messages, *, temperature=None, max_tokens=None):
		self.calls += 1
		hard_requirement = "年龄 25 岁以下" if self.protected else "熟练使用 Python"
		return json.dumps(
			{
				"title": "Python 后端工程师",
				"hard_requirements": [{"requirement": hard_requirement, "required": True}],
				"dimensions": [
					{"name": "backend_evidence", "max_score": 60, "description": "后端项目和职责证据"},
					{"name": "reliability_evidence", "max_score": 40, "description": "稳定性与测试证据"},
				],
				"thresholds": {"strong_interview": 85, "interview": 70, "manual_review": 55},
				"max_questions": 5,
				"persona_summary": "关注可验证的后端工程与稳定性经验",
				"suggested_questions": ["请说明一次后端稳定性优化的具体证据"],
			},
			ensure_ascii=False,
		)


def test_autopilot_generates_profile_once_and_refreshes_when_jd_changes(tmp_path: Path):
	platform = FakePlatform()
	service = FakeService()
	store = RecruiterAIStore(tmp_path)

	first = prepare_autopilot_job_profiles(
		platform=platform,
		store=store,
		service=service,
		auto_configure=True,
	)
	assert service.calls == 1
	assert first["updated"][0]["reason"] == "initial_ai_profile"
	job = store.list_jobs()[0]
	assert job["metadata"]["autopilot_profile_generated"] is True
	assert job["metadata"]["title"] == "Python 后端工程师"
	assert [item["name"] for item in job["rubric"]["dimensions"]] == ["backend_evidence", "reliability_evidence"]

	second = prepare_autopilot_job_profiles(
		platform=platform,
		store=store,
		service=service,
		auto_configure=True,
	)
	assert service.calls == 1
	assert second["updated"] == []

	platform.jd = "负责 Python 后端、分布式任务、测试与稳定性优化。"
	third = prepare_autopilot_job_profiles(
		platform=platform,
		store=store,
		service=service,
		auto_configure=True,
	)
	assert service.calls == 2
	assert third["updated"][0]["reason"] == "jd_changed"
	assert store.list_jobs()[0]["jd_text"] == platform.jd


def test_autopilot_rejects_protected_profile_and_keeps_safe_existing_job(tmp_path: Path):
	platform = FakePlatform()
	service = FakeService(protected=True)
	store = RecruiterAIStore(tmp_path)

	result = prepare_autopilot_job_profiles(
		platform=platform,
		store=store,
		service=service,
		auto_configure=True,
	)
	assert result["updated"] == []
	assert result["warnings"]
	job = store.list_jobs()[0]
	assert job["metadata"].get("autopilot_profile_generated") is not True
	assert all("年龄" not in item.get("requirement", "") for item in job["rubric"]["hard_requirements"])
