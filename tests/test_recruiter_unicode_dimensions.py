from boss_agent_cli.recruiter_ai import normalize_rubric, validate_evaluation


def test_chinese_dimension_name_remains_matchable() -> None:
	rubric = normalize_rubric({
		"dimensions": [
			{"name": "后端经验", "max_score": 60, "description": "后端工程经验"},
			{"name": "项目复杂度", "max_score": 40, "description": "复杂项目证据"},
		],
	})
	result = validate_evaluation({
		"confidence": 0.9,
		"dimensions": [
			{"name": "后端经验", "score": 54, "max_score": 60, "reason": "经验充分", "evidence": ["5年 Java 后端经验"]},
			{"name": "项目复杂度", "score": 32, "max_score": 40, "reason": "复杂度较高", "evidence": ["负责高并发订单系统"]},
		],
		"hard_requirements": [],
		"strengths": [],
		"concerns": [],
		"next_questions": [],
		"summary": "岗位匹配",
	}, rubric)

	assert [item["name"] for item in result["dimensions"]] == ["后端经验", "项目复杂度"]
	assert result["total_score"] == 86


def test_chinese_dimension_punctuation_normalizes_without_losing_text() -> None:
	rubric = normalize_rubric({
		"dimensions": [{"name": "项目-复杂度", "max_score": 100, "description": "复杂项目证据"}],
	})
	result = validate_evaluation({
		"confidence": 0.9,
		"dimensions": [
			{"name": "项目 复杂度", "score": 80, "max_score": 100, "reason": "匹配", "evidence": ["高并发系统"]},
		],
		"hard_requirements": [],
		"strengths": [],
		"concerns": [],
		"next_questions": [],
		"summary": "岗位匹配",
	}, rubric)
	assert result["total_score"] == 80
