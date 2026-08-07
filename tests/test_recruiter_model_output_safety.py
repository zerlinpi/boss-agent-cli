from boss_agent_cli.recruiter_ai import normalize_rubric, validate_evaluation


def test_protected_model_evidence_is_removed_and_cannot_support_score() -> None:
	rubric = normalize_rubric({
		"dimensions": [{"name": "required_skills", "max_score": 100, "description": "必需技能"}],
	})
	result = validate_evaluation({
		"confidence": 0.9,
		"hard_requirements": [],
		"dimensions": [{
			"name": "required_skills",
			"score": 100,
			"max_score": 100,
			"reason": "年龄较小，学习能力强",
			"evidence": ["候选人 28岁"],
		}],
		"strengths": ["年轻有活力", "Java 项目经验丰富"],
		"concerns": ["已婚可能不稳定"],
		"next_questions": ["你结婚了吗？", "请介绍订单系统 QPS"],
		"summary": "男性，建议直接面试",
	}, rubric)

	assert result["total_score"] == 0
	assert result["recommendation"] == "manual_review"
	assert result["dimensions"][0]["evidence"] == []
	assert result["dimensions"][0]["score"] == 0.0
	assert result["strengths"] == ["Java 项目经验丰富"]
	assert result["concerns"] == []
	assert result["next_questions"] == ["请介绍订单系统 QPS"]
	assert result["model_output_sanitized"] is True
	assert result["safety_flags"] == ["protected_or_contact_content_removed"]


def test_safe_model_output_keeps_normal_recommendation() -> None:
	rubric = normalize_rubric({
		"dimensions": [{"name": "required_skills", "max_score": 100, "description": "必需技能"}],
	})
	result = validate_evaluation({
		"confidence": 0.9,
		"hard_requirements": [],
		"dimensions": [{
			"name": "required_skills",
			"score": 90,
			"max_score": 100,
			"reason": "有明确 Java 项目证据",
			"evidence": ["负责 Spring Boot 订单系统"],
		}],
		"strengths": ["Java 项目经验丰富"],
		"concerns": [],
		"next_questions": ["请说明订单系统峰值 QPS"],
		"summary": "建议人工复核后进入面试",
	}, rubric)

	assert result["total_score"] == 90
	assert result["recommendation"] == "strong_interview"
	assert result["model_output_sanitized"] is False
	assert result["safety_flags"] == []
