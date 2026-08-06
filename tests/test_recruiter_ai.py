import json
from pathlib import Path
from typing import Any

from boss_agent_cli.recruiter_ai import (
	RecruiterAIStore,
	candidate_name,
	evaluate_resume,
	normalize_resume,
	parse_ai_json,
	summarize_ranking,
)


class FakeAIService:
	def __init__(self, payload: dict[str, Any]):
		self.payload = payload
		self.messages: list[dict[str, str]] = []

	def chat(
		self,
		messages: list[dict[str, Any]],
		*,
		temperature: float | None = None,
		max_tokens: int | None = None,
	) -> str:
		self.messages = [{"role": str(item["role"]), "content": str(item["content"])} for item in messages]
		return json.dumps(self.payload, ensure_ascii=False)


def _evaluation(score: int, recommendation: str = "interview") -> dict[str, Any]:
	return {
		"candidate_name": "张三",
		"total_score": score,
		"recommendation": recommendation,
		"confidence": 0.8,
		"hard_requirements": [],
		"dimensions": [],
		"strengths": ["Java"],
		"concerns": [],
		"next_questions": [],
		"summary": "建议人工复核后进入面试。",
	}


def test_normalize_resume_strips_protected_attributes() -> None:
	payload = {
		"ok": True,
		"data": {
			"basic": {
				"name": "张三",
				"gender": "男",
				"age": "28岁",
				"avatar": "https://example.com/avatar.png",
				"degree": "本科",
			},
			"work_experience": [],
		},
	}

	result = normalize_resume(payload)

	assert result["basic"] == {"name": "张三", "degree": "本科"}
	assert candidate_name(result) == "张三"


def test_parse_ai_json_accepts_markdown_fence() -> None:
	result = parse_ai_json('```json\n{"total_score": 88}\n```')
	assert result["total_score"] == 88


def test_evaluate_resume_marks_human_review_required() -> None:
	service = FakeAIService(_evaluation(86))
	resume = {"basic": {"name": "张三"}, "work_experience": []}

	result = evaluate_resume(service, "Java 后端开发", resume)  # type: ignore[arg-type]

	assert result["total_score"] == 86
	assert result["human_review_required"] is True
	assert result["candidate_name"] == "张三"
	assert "不得依据性别" in service.messages[0]["content"]
	assert "张三" not in service.messages[1]["content"]


def test_store_ranks_by_total_score(tmp_path: Path) -> None:
	store = RecruiterAIStore(tmp_path)
	resume_a = {"basic": {"name": "候选人A"}}
	resume_b = {"basic": {"name": "候选人B"}}
	store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume=resume_a,
		evaluation=_evaluation(70),
	)
	store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume=resume_b,
		evaluation=_evaluation(90, "strong_interview"),
	)

	ranking = summarize_ranking(store.rank(job_key="java", top=10))

	assert [item["candidate_name"] for item in ranking] == ["候选人B", "候选人A"]
	assert [item["rank"] for item in ranking] == [1, 2]
