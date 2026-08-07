import json
from pathlib import Path
from typing import Any

import pytest

from boss_agent_cli.recruiter_ai import (
	CANDIDATE_STATUSES,
	DEFAULT_DIMENSIONS,
	RecruiterAIError,
	RecruiterAIStore,
	candidate_items,
	candidate_name,
	conversation_to_text,
	evaluate_resume,
	extract_candidate_ref,
	normalize_resume,
	normalize_rubric,
	parse_ai_json,
	recommended_reply_intent,
	redact_resume_for_model,
	summarize_ranking,
	validate_evaluation,
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


def _dimensions(total: int) -> list[dict[str, Any]]:
	remaining = total
	result: list[dict[str, Any]] = []
	for spec in DEFAULT_DIMENSIONS:
		max_score = int(spec["max_score"])
		score = min(max_score, remaining)
		remaining -= score
		result.append({
			"name": spec["name"],
			"score": score,
			"max_score": max_score,
			"reason": "有简历证据",
			"evidence": [f"{spec['name']} evidence"],
		})
	return result


def _evaluation(score: int, *, hard_status: str = "met") -> dict[str, Any]:
	return {
		"total_score": score,
		"recommendation": "interview",
		"confidence": 0.8,
		"hard_requirements": [
			{"requirement": "Java", "status": hard_status, "evidence": ["Java 项目经验"]}
		],
		"dimensions": _dimensions(score),
		"strengths": ["Java"],
		"concerns": [],
		"next_questions": [],
		"summary": "建议人工复核后进入面试。",
	}


def test_normalize_resume_keeps_local_recruiter_data_but_model_copy_redacts_it() -> None:
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
			"contact": {"phone": "13800000000", "email": "a@example.com"},
			"work_experience": [],
		},
	}

	result = normalize_resume(payload)

	assert result["basic"]["name"] == "张三"
	assert result["basic"]["gender"] == "男"
	assert result["basic"]["age"] == "28岁"
	assert result["basic"]["degree"] == "本科"
	assert result["contact"]["phone"] == "13800000000"
	assert candidate_name(result) == "张三"

	model_copy = redact_resume_for_model(result)
	serialized = json.dumps(model_copy, ensure_ascii=False)
	for private_value in ("张三", "男", "28岁", "13800000000", "a@example.com"):
		assert private_value not in serialized
	assert "本科" in serialized


def test_parse_ai_json_accepts_fence_and_leading_text() -> None:
	assert parse_ai_json('```json\n{"total_score": 88}\n```')["total_score"] == 88
	assert parse_ai_json('结果如下：\n{"total_score": 89}')["total_score"] == 89


def test_evaluate_resume_recomputes_score_and_redacts_identity() -> None:
	service = FakeAIService(_evaluation(86))
	resume = {"basic": {"name": "张三", "gender": "男"}, "work_experience": []}

	result = evaluate_resume(service, "Java 后端开发", resume)  # type: ignore[arg-type]

	assert result["total_score"] == 86
	assert result["recommendation"] == "strong_interview"
	assert result["human_review_required"] is True
	assert result["candidate_name"] == "张三"
	assert "不得依据性别" in service.messages[0]["content"]
	assert "张三" not in service.messages[1]["content"]


def test_redact_resume_for_model_scrubs_free_text_identity_and_contacts() -> None:
	resume = {
		"basic": {"name": "张三", "degree": "本科"},
		"raw_text": (
			"张三，手机 138-0000-0000，座机 010-12345678，邮箱 zhangsan@example.com，"
			"微信 weixin: zhangsan88，QQ: 12345678，身份证 110101199001011234。"
		),
		"work_experience": [{"description": "张三负责 Java 订单系统"}],
	}

	redacted = redact_resume_for_model(resume)
	serialized = json.dumps(redacted, ensure_ascii=False)

	for secret in (
		"张三", "138-0000-0000", "010-12345678", "zhangsan@example.com", "zhangsan88",
		"12345678", "110101199001011234",
	):
		assert secret not in serialized
	assert "[姓名已脱敏]" in serialized
	assert "[手机号已脱敏]" in serialized
	assert "[座机已脱敏]" in serialized
	assert "[邮箱已脱敏]" in serialized
	assert "[身份证号已脱敏]" in serialized


def test_normalize_rubric_rejects_invalid_numeric_contracts() -> None:
	for value in (0, -1, 0.5, float("nan"), float("inf"), True):
		with pytest.raises(RecruiterAIError):
			normalize_rubric({"dimensions": [{"name": "skills", "max_score": value}]})

	for value in (-1, 50.5, float("nan"), float("inf"), True):
		with pytest.raises(RecruiterAIError):
			normalize_rubric({"thresholds": {"manual_review": value}})

	for value in ("many", 1.5, float("nan"), True):
		with pytest.raises(RecruiterAIError):
			normalize_rubric({"max_questions": value})


def test_normalize_rubric_accepts_integral_floats_and_deduplicates_hard_requirements() -> None:
	rubric = normalize_rubric({
		"dimensions": [{"name": "skills", "max_score": 100.0}],
		"thresholds": {"manual_review": 50.0, "interview": 70.0, "strong_interview": 85.0},
		"hard_requirements": ["Java", " Java ", "", {"requirement": "Java"}, {"requirement": "Python"}],
		"max_questions": "6",
	})
	assert rubric["dimensions"][0]["max_score"] == 100
	assert rubric["thresholds"]["interview"] == 70
	assert rubric["hard_requirements"] == [
		{"requirement": "Java", "required": True},
		{"requirement": "Python", "required": True},
	]
	assert rubric["max_questions"] == 6


def test_missing_hard_requirement_forces_manual_review() -> None:
	rubric = normalize_rubric({"hard_requirements": ["Java"]})
	result = validate_evaluation(_evaluation(95, hard_status="missing"), rubric)

	assert result["total_score"] == 95
	assert result["recommendation"] == "manual_review"
	assert result["human_review_required"] is True


def test_store_skips_unchanged_and_ranks_latest(tmp_path: Path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="JD", rubric=rubric)
	resume_a = {"basic": {"name": "候选人A"}, "work_experience": []}
	resume_b = {"basic": {"name": "候选人B"}, "work_experience": []}
	first = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume=resume_a,
		evaluation=validate_evaluation(_evaluation(70), rubric),
		source={"type": "zhipin", "friend_id": 1},
		rubric=rubric,
	)
	store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume=resume_b,
		evaluation=validate_evaluation(_evaluation(90), rubric),
		source={"type": "zhipin", "friend_id": 2},
		rubric=rubric,
	)

	unchanged = store.find_unchanged(
		job_key="java",
		resume=resume_a,
		source={"type": "zhipin", "friend_id": 1},
		rubric=rubric,
	)
	ranking = summarize_ranking(store.rank(job_key="java", top=10))

	assert unchanged is not None
	assert unchanged["id"] == first["id"]
	assert [item["candidate_name"] for item in ranking] == ["候选人B", "候选人A"]
	assert [item["rank"] for item in ranking] == [1, 2]


def test_store_status_and_report(tmp_path: Path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	record = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "候选人A"}},
		evaluation=validate_evaluation(_evaluation(80), rubric),
		rubric=rubric,
	)
	store.set_status(record["id"], "interview", note="技术初面")
	report = store.report(job_key="java", top=10)

	assert report["total_candidates"] == 1
	assert report["status_counts"]["interview"] == 1
	assert report["top_candidates"][0]["status"] == "interview"
	assert set(report["status_counts"]) == CANDIDATE_STATUSES


def test_candidate_reference_and_chat_normalization() -> None:
	payload = {
		"friendList": [{
			"friendId": 123,
			"geekCard": {"geekId": "g1", "securityId": "s1", "name": "候选人A"},
			"jobCard": {"encJobId": "j1"},
		}],
	}
	items = candidate_items(payload)
	ref = extract_candidate_ref(items[0])
	conversation = conversation_to_text({
		"messages": [
			{"from": {"name": "候选人"}, "content": "我对岗位感兴趣"},
			{"from": {"name": "招聘者"}, "content": "请发简历"},
		]
	})

	assert ref["geek_id"] == "g1"
	assert ref["security_id"] == "s1"
	assert ref["job_id"] == "j1"
	assert ref["friend_id"] == 123
	assert "候选人: 我对岗位感兴趣" in conversation


def test_recommended_reply_intent_prefers_questions() -> None:
	assert recommended_reply_intent({
		"recommendation": "strong_interview",
		"next_questions": ["项目 QPS 是多少？"],
	}) == "ask_followup"
	assert recommended_reply_intent({
		"recommendation": "interview",
		"next_questions": [],
	}) == "invite_interview"
