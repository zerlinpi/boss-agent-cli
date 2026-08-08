import json

from boss_agent_cli.commands.recruiter.ai_common import evaluate_local
from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric


class FakeService:
	def __init__(self) -> None:
		self.calls = 0

	def chat(self, messages, *, temperature=None, max_tokens=None):
		self.calls += 1
		return json.dumps({
			"confidence": 0.8,
			"dimensions": [{
				"name": "required_skills",
				"score": 80,
				"max_score": 100,
				"reason": "Java 经验匹配",
				"evidence": ["5年 Java 经验"],
			}],
			"hard_requirements": [],
			"strengths": ["Java"],
			"concerns": [],
			"next_questions": [],
			"summary": "岗位匹配",
		}, ensure_ascii=False)


def _rubric():
	return normalize_rubric({
		"dimensions": [{"name": "required_skills", "max_score": 100, "description": "岗位必需技能"}],
	})


def test_cli_incremental_cache_scans_once_and_reuses_unchanged_result(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	service = FakeService()
	rubric = _rubric()
	resume = {"basic": {"name": "候选人A"}, "raw_text": "5年 Java 经验"}
	source = {"type": "local", "path": str(tmp_path / "candidate-a.json")}

	original_latest = store.latest_by_candidate
	calls = 0

	def counted_latest(*, job_key):
		nonlocal calls
		calls += 1
		return original_latest(job_key=job_key)

	store.latest_by_candidate = counted_latest  # type: ignore[method-assign]

	first = evaluate_local(
		service=service,
		store=store,
		jd_text="Java 后端工程师",
		rubric=rubric,
		resume_payload=resume,
		job_key="java",
		source=source,
		save=True,
	)
	second = evaluate_local(
		service=service,
		store=store,
		jd_text="Java 后端工程师",
		rubric=rubric,
		resume_payload=resume,
		job_key="java",
		source=source,
		save=True,
	)

	assert first["skipped"] is False
	assert second["skipped"] is True
	assert second["id"] == first["id"]
	assert service.calls == 1
	assert calls == 1


def test_cli_incremental_cache_re_evaluates_when_inline_jd_changes(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	service = FakeService()
	rubric = _rubric()
	resume = {"basic": {"name": "候选人A"}, "raw_text": "5年 Java 经验"}
	source = {"type": "local", "path": str(tmp_path / "candidate-a.json")}

	first = evaluate_local(
		service=service,
		store=store,
		jd_text="负责 Java API 开发",
		rubric=rubric,
		resume_payload=resume,
		job_key="java",
		source=source,
		save=True,
	)
	second = evaluate_local(
		service=service,
		store=store,
		jd_text="负责 Java API 与 Kafka 高并发链路",
		rubric=rubric,
		resume_payload=resume,
		job_key="java",
		source=source,
		save=True,
	)

	assert first["id"] != second["id"]
	assert second["skipped"] is False
	assert service.calls == 2


def test_saved_job_jd_change_invalidates_store_unchanged_lookup(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	service = FakeService()
	rubric = _rubric()
	resume = {"basic": {"name": "候选人A"}, "raw_text": "5年 Java 经验"}
	source = {"type": "local", "path": str(tmp_path / "candidate-a.json")}

	store.save_job(job_key="java", jd_text="旧 JD", rubric=rubric)
	evaluate_local(
		service=service,
		store=store,
		jd_text="旧 JD",
		rubric=rubric,
		resume_payload=resume,
		job_key="java",
		source=source,
		save=True,
	)
	assert store.find_unchanged(job_key="java", resume=resume, source=source, rubric=rubric) is not None

	store.save_job(job_key="java", jd_text="新 JD，新增 Kafka 责任", rubric=rubric)
	assert store.find_unchanged(job_key="java", resume=resume, source=source, rubric=rubric) is None
