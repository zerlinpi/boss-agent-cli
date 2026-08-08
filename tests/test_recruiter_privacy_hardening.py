import json

import pytest

from boss_agent_cli.recruiter_ai import (
	RecruiterAIError,
	RecruiterAIStore,
	normalize_resume,
	normalize_rubric,
	redact_contact_text,
	redact_resume_for_model,
	validate_evaluation,
)


def _rubric():
	return normalize_rubric({
		"dimensions": [
			{"name": "required_skills", "max_score": 100, "description": "岗位必需技能"},
		],
		"hard_requirements": [],
	})


def test_rubric_rejects_age_generation_and_canonical_duplicate_dimensions() -> None:
	with pytest.raises(RecruiterAIError, match="代理条件"):
		normalize_rubric({"title": "90后 Java 工程师"})

	with pytest.raises(RecruiterAIError, match="归一化后不能重复"):
		normalize_rubric({
			"dimensions": [
				{"name": "required_skills", "max_score": 50},
				{"name": "RequiredSkills", "max_score": 50},
			],
		})

	with pytest.raises(RecruiterAIError, match="硬性要求归一化后不能重复"):
		normalize_rubric({
			"hard_requirements": ["Java", " java "],
		})


def test_model_text_redaction_covers_vague_protected_preferences() -> None:
	text = "年龄偏好，性别要求，婚姻稳定优先，你结婚了吗？有没有孩子？5年 Java 经验"
	redacted = redact_contact_text(text)

	for secret in ("年龄偏好", "性别要求", "婚姻稳定优先", "结婚了吗", "有没有孩子"):
		assert secret not in redacted
	assert "5年 Java 经验" in redacted


def test_resume_model_payload_uses_same_vague_preference_redaction() -> None:
	resume = normalize_resume({
		"basic": {"name": "张三"},
		"raw_text": "年龄偏好：年轻优先；婚姻稳定优先；5年 Java 经验",
	})
	payload = json.dumps(redact_resume_for_model(resume), ensure_ascii=False)

	assert "年龄偏好" not in payload
	assert "年轻优先" not in payload
	assert "婚姻稳定优先" not in payload
	assert "5年 Java 经验" in payload


def test_model_output_unsafe_evidence_is_removed_before_score_recomputation() -> None:
	result = validate_evaluation(
		{
			"confidence": 0.9,
			"dimensions": [
				{
					"name": "RequiredSkills",
					"score": 100,
					"max_score": 100,
					"reason": "年龄较小，适合团队",
					"evidence": ["年龄较小"],
				},
			],
			"hard_requirements": [
				{"requirement": "男性优先", "status": "met", "evidence": ["男性"]},
			],
			"strengths": ["5年 Java 经验"],
			"concerns": ["年龄较小", "需要确认高并发项目规模"],
			"next_questions": ["你结婚了吗？", "请介绍最近的 Java 项目"],
			"summary": "90后候选人，Java 项目经验较多",
		},
		_rubric(),
	)

	assert result["total_score"] == 0
	assert result["dimensions"][0]["evidence"] == []
	assert result["hard_requirements"] == []
	assert result["strengths"] == ["5年 Java 经验"]
	assert result["concerns"] == ["需要确认高并发项目规模"]
	assert result["next_questions"] == ["请介绍最近的 Java 项目"]
	assert result["recommendation"] == "manual_review"
	assert result["model_output_sanitized"] is True
	assert result["model_output_safety_flags"] == [
		"protected_or_contact_content",
		"unexpected_hard_requirement",
	]


def test_safe_model_output_keeps_evidence_and_score() -> None:
	result = validate_evaluation(
		{
			"confidence": 0.9,
			"dimensions": [
				{
					"name": "required-skills",
					"score": 90,
					"max_score": 100,
					"reason": "Java 和 Spring Boot 生产经验充分",
					"evidence": ["5年 Java 经验", "负责 Spring Boot 订单系统"],
				},
			],
			"hard_requirements": [],
			"strengths": ["高并发订单系统经验"],
			"concerns": [],
			"next_questions": ["请介绍一次线上故障排查经历"],
			"summary": "技术经历与岗位要求匹配",
		},
		_rubric(),
	)

	assert result["total_score"] == 90
	assert result["dimensions"][0]["evidence"] == ["5年 Java 经验", "负责 Spring Boot 订单系统"]
	assert result["recommendation"] == "strong_interview"
	assert "model_output_sanitized" not in result


def test_reply_persistence_keeps_contacts_but_drops_identity_and_home_address(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = _rubric()
	evaluation = validate_evaluation({
		"confidence": 0.8,
		"dimensions": [{
			"name": "required_skills",
			"score": 80,
			"max_score": 100,
			"reason": "Java 经验匹配",
			"evidence": ["5年 Java 经验"],
		}],
		"hard_requirements": [],
		"strengths": [],
		"concerns": [],
		"next_questions": [],
		"summary": "岗位匹配",
	}, rubric)
	record = store.save_evaluation(
		job_key="java",
		jd_text="Java 工程师",
		resume={"basic": {"name": "张三"}},
		evaluation=evaluation,
		rubric=rubric,
	)
	conversation = (
		"电话 13800000000，微信：zhang_wechat，身份证 110101199001011234，"
		"护照号 E12345678，家庭住址：上海市浦东新区世纪大道100号，"
		"面试地址：上海市徐汇区公司会议室"
	)
	reply = store.save_reply(
		evaluation_id=record["id"],
		intent="invite_interview",
		conversation=conversation,
		draft={"reply": "方便约个时间面试吗？"},
	)

	assert "13800000000" in reply["conversation"]
	assert "zhang_wechat" in reply["conversation"]
	assert "110101199001011234" not in reply["conversation"]
	assert "E12345678" not in reply["conversation"]
	assert "世纪大道100号" not in reply["conversation"]
	assert "面试地址：上海市徐汇区公司会议室" in reply["conversation"]
	assert reply["local_conversation_sanitized"] is True

	stored = json.loads((store.replies_dir / f"{reply['id']}.json").read_text(encoding="utf-8"))
	assert stored["conversation"] == reply["conversation"]
	assert "110101199001011234" not in stored["conversation"]
