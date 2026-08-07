from boss_agent_cli.recruiter_ai import normalize_rubric, validate_evaluation


def _dimensions(score: int):
	return [
		{
			"name": "required_skills",
			"score": score,
			"max_score": 30,
			"reason": "有证据",
			"evidence": ["Java 项目经验"],
		},
		{
			"name": "relevant_experience",
			"score": 20,
			"max_score": 20,
			"reason": "有证据",
			"evidence": ["5 年相关经验"],
		},
		{
			"name": "project_evidence",
			"score": 15,
			"max_score": 15,
			"reason": "有证据",
			"evidence": ["订单系统项目"],
		},
		{
			"name": "responsibility_match",
			"score": 15,
			"max_score": 15,
			"reason": "有证据",
			"evidence": ["后端职责"],
		},
		{
			"name": "industry_match",
			"score": 10,
			"max_score": 10,
			"reason": "有证据",
			"evidence": ["电商业务"],
		},
		{
			"name": "achievement_evidence",
			"score": 10,
			"max_score": 10,
			"reason": "有证据",
			"evidence": ["性能提升 30%"],
		},
	]


def test_hard_requirement_matches_case_and_whitespace_and_keeps_configured_label() -> None:
	rubric = normalize_rubric({"hard_requirements": ["Java"]})
	result = validate_evaluation({
		"confidence": 0.9,
		"hard_requirements": [
			{"requirement": "  java  ", "status": "met", "evidence": ["5 年 Java 项目经验"]},
		],
		"dimensions": _dimensions(30),
	}, rubric)

	assert result["total_score"] == 100
	assert result["recommendation"] == "strong_interview"
	assert result["hard_requirements"] == [
		{"requirement": "Java", "status": "met", "evidence": ["5 年 Java 项目经验"]},
	]


def test_hard_requirement_missing_still_forces_manual_review_after_normalization() -> None:
	rubric = normalize_rubric({"hard_requirements": ["Java"]})
	result = validate_evaluation({
		"confidence": 0.9,
		"hard_requirements": [
			{"requirement": " JAVA ", "status": "missing", "evidence": []},
		],
		"dimensions": _dimensions(30),
	}, rubric)

	assert result["total_score"] == 100
	assert result["recommendation"] == "manual_review"
