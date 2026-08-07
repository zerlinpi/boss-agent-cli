from boss_agent_cli.recruiter_ai import normalize_rubric, validate_evaluation


def test_model_dimension_names_match_case_spaces_and_hyphens() -> None:
	rubric = normalize_rubric({
		"dimensions": [
			{"name": "required_skills", "max_score": 60, "description": "必需技能"},
			{"name": "project-evidence", "max_score": 40, "description": "项目证据"},
		],
	})
	result = validate_evaluation({
		"confidence": 0.9,
		"hard_requirements": [],
		"dimensions": [
			{
				"name": "Required Skills",
				"score": 60,
				"max_score": 60,
				"reason": "匹配",
				"evidence": ["Java"],
			},
			{
				"name": "PROJECT EVIDENCE",
				"score": 40,
				"max_score": 40,
				"reason": "匹配",
				"evidence": ["订单系统"],
			},
		],
	}, rubric)

	assert result["total_score"] == 100
	assert result["recommendation"] == "strong_interview"
	assert [item["name"] for item in result["dimensions"]] == ["required_skills", "project-evidence"]
	assert [item["score"] for item in result["dimensions"]] == [60.0, 40.0]


def test_unknown_model_dimension_cannot_add_score() -> None:
	rubric = normalize_rubric({
		"dimensions": [{"name": "required_skills", "max_score": 100, "description": "必需技能"}],
	})
	result = validate_evaluation({
		"confidence": 0.8,
		"hard_requirements": [],
		"dimensions": [
			{
				"name": "personality_bonus",
				"score": 100,
				"max_score": 100,
				"reason": "模型自行增加的维度",
				"evidence": ["irrelevant"],
			},
		],
	}, rubric)

	assert result["total_score"] == 0
	assert result["dimensions"][0]["name"] == "required_skills"
	assert result["dimensions"][0]["score"] == 0.0
