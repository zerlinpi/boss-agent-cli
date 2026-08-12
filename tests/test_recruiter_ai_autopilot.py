import json
from pathlib import Path

from boss_agent_cli.commands.recruiter import ai_autopilot
from boss_agent_cli.recruiter_ai import RecruiterAIStore


class FakePlatform:
	def __init__(self) -> None:
		self.friend_calls: list[tuple[int, str]] = []
		self.view_calls = 0

	def is_success(self, response):
		return response.get("code") == 0

	def unwrap_data(self, response):
		return response.get("zpData")

	def parse_error(self, response):
		return "ERROR", str(response.get("message") or "failed")

	def list_jobs(self):
		return {
			"code": 0,
			"zpData": {
				"jobList": [
					{"encryptJobId": "enc-job-1", "jobName": "Backend Engineer"},
				]
			},
		}

	def job_detail(self, enc_job_id):
		assert enc_job_id == "enc-job-1"
		return {
			"code": 0,
			"zpData": {
				"job": {
					"encryptJobId": enc_job_id,
					"jobName": "Backend Engineer",
					"jobDescription": "负责 Python 后端服务开发、测试和性能优化。",
				}
			},
		}

	def friend_list(self, page=1, label_id=0, job_id=None):
		self.friend_calls.append((page, str(job_id or "")))
		if page == 1:
			return {
				"code": 0,
				"zpData": {
					"friendList": [
						{
							"geekId": "geek-1",
							"securityId": "security-1",
							"friendId": 101,
							"encryptJobId": "enc-job-1",
							"geekName": "Candidate A",
						}
					]
				},
			}
		return {"code": 0, "zpData": {"friendList": []}}

	def view_geek(self, geek_id, job_id, security_id=None):
		self.view_calls += 1
		return {"code": 0, "zpData": {"geekId": geek_id, "jobId": job_id, "securityId": security_id}}


class DuplicatePagePlatform(FakePlatform):
	def friend_list(self, page=1, label_id=0, job_id=None):
		self.friend_calls.append((page, str(job_id or "")))
		return {
			"code": 0,
			"zpData": {
				"friendList": [
					{"geekId": "same", "securityId": "sec", "friendId": 1, "encryptJobId": job_id}
				]
			},
		}


class FakeService:
	def __init__(self) -> None:
		self.calls = 0

	def chat(self, messages, *, temperature=None):
		self.calls += 1
		assert messages
		assert temperature == 0.1
		return json.dumps({
			"title": "Backend Engineer",
			"hard_requirements": [{"requirement": "Python 后端开发", "required": True}],
			"dimensions": [
				{"name": "required_skills", "max_score": 60, "description": "Python 后端技能证据"},
				{"name": "relevant_experience", "max_score": 40, "description": "相关项目和职责证据"},
			],
			"thresholds": {"strong_interview": 85, "interview": 70, "manual_review": 55},
			"max_questions": 4,
			"persona_summary": "需要 Python 后端服务开发和优化经验",
			"suggested_questions": ["请说明一个后端性能优化案例"],
		}, ensure_ascii=False)


def test_extract_platform_jobs_handles_nested_payload_and_deduplicates():
	payload = {
		"groups": [
			{"jobs": [{"encryptJobId": "j1", "jobName": "One"}]},
			{"jobs": [{"encryptJobId": "j1", "jobName": "One duplicate"}]},
			{"jobs": [{"encJobId": "j2", "jobTitle": "Two"}]},
			{"encryptId": "not-a-job"},
		]
	}
	assert ai_autopilot.extract_platform_jobs(payload) == [
		{"job_id": "j2", "title": "Two"},
		{"job_id": "j1", "title": "One duplicate"},
	]


def test_extract_job_description_prefers_longest_explicit_description():
	payload = {
		"job": {"jobDesc": "short"},
		"detail": {"jobDescription": "负责 Python 后端服务开发、测试、稳定性和性能优化。"},
	}
	assert ai_autopilot.extract_job_description(payload).startswith("负责 Python")


def test_collect_candidate_refs_stops_when_endpoint_repeats_same_page():
	platform = DuplicatePagePlatform()
	refs, failures, pages_read = ai_autopilot._collect_candidate_refs(
		platform=platform,
		job_id="enc-job-1",
		max_pages=50,
		max_candidates=100,
	)
	assert failures == []
	assert len(refs) == 1
	assert pages_read == 2
	assert len(platform.friend_calls) == 2


def test_corrupt_autopilot_state_is_rebuilt_without_touching_evaluations(tmp_path: Path):
	state_path = tmp_path / "recruiter-ai" / "autopilot-state.json"
	state_path.parent.mkdir(parents=True)
	state_path.write_text("{broken", encoding="utf-8")
	evaluation = state_path.parent / "evaluations" / "eval_keep.json"
	evaluation.parent.mkdir(parents=True)
	evaluation.write_text('{"id":"eval_keep"}', encoding="utf-8")

	state = ai_autopilot.RecruiterAutopilotState(tmp_path)
	assert state.payload["candidates"] == {}
	assert evaluation.read_text(encoding="utf-8") == '{"id":"eval_keep"}'
	assert list(state_path.parent.glob("autopilot-state.json.corrupt-*"))


def test_run_autopilot_auto_configures_job_and_skips_recent_candidate(monkeypatch, tmp_path: Path):
	platform = FakePlatform()
	service = FakeService()
	store = RecruiterAIStore(tmp_path)

	monkeypatch.setattr(
		ai_autopilot,
		"parse_resume",
		lambda _payload: {"basic": {"name": "Candidate A"}, "skills": ["Python"]},
	)

	def fake_evaluate_local(**kwargs):
		record = kwargs["store"].save_evaluation(
			job_key=kwargs["job_key"],
			jd_text=kwargs["jd_text"],
			resume=kwargs["resume_payload"],
			evaluation={
				"total_score": 88,
				"confidence": 0.9,
				"recommendation": "interview",
				"strengths": ["Python"],
				"concerns": [],
				"next_questions": [],
				"summary": "good",
			},
			source=kwargs["source"],
			rubric=kwargs["rubric"],
		)
		record.update({"saved": True, "skipped": False})
		return record

	monkeypatch.setattr(ai_autopilot, "evaluate_local", fake_evaluate_local)

	first = ai_autopilot.run_autopilot(
		data_dir=tmp_path,
		platform=platform,
		service=service,
		store=store,
		max_pages=10,
		max_candidates_per_job=100,
		refresh_seen_hours=24,
		top=20,
		draft_top=0,
		include_chat=False,
		force=False,
		auto_configure=True,
		selected_job_keys=None,
	)
	assert first["totals"]["jobs_processed"] == 1
	assert first["totals"]["evaluated"] == 1
	assert platform.view_calls == 1
	assert service.calls == 1
	jobs = store.list_jobs()
	assert len(jobs) == 1
	assert jobs[0]["metadata"]["boss_job_id"] == "enc-job-1"

	second = ai_autopilot.run_autopilot(
		data_dir=tmp_path,
		platform=platform,
		service=service,
		store=store,
		max_pages=10,
		max_candidates_per_job=100,
		refresh_seen_hours=24,
		top=20,
		draft_top=0,
		include_chat=False,
		force=False,
		auto_configure=True,
		selected_job_keys=None,
	)
	assert second["totals"]["evaluated"] == 0
	assert second["totals"]["freshness_skipped"] == 1
	assert platform.view_calls == 1
	assert service.calls == 1
	assert second["messages_sent"] == 0
	assert second["final_employment_decisions_automated"] is False
