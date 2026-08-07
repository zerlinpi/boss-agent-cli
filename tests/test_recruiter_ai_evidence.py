import math

from boss_agent_cli.recruiter_ai import normalize_rubric, validate_evaluation


def _dimensions(rubric, *, score: int | float, evidence: list[str]):
	return [
		{
			"name": item["name"],
			"score": min(score, item["max_score"]),
			"max_score": item["max_score"],
			"reason": "model reason",
			"evidence": evidence,
		}
		for item in rubric["dimensions"]
	]


def test_positive_dimension_score_without_evidence_is_zeroed():
	rubric = normalize_rubric()
	result = validate_evaluation({
		"confidence": 0.9,
		"hard_requirements": [],
		"dimensions": _dimensions(rubric, score=10, evidence=[]),
		"strengths": [],
		"concerns": [],
		"next_questions": [],
		"summary": "",
	}, rubric)

	assert result["total_score"] == 0
	assert all(item["score"] == 0 for item in result["dimensions"])
	assert result["evidence_coverage"] == 0
	assert result["score_source"] == "evidence_backed_dimension_sum"


def test_hard_requirement_marked_met_without_evidence_becomes_unclear():
	rubric = normalize_rubric({"hard_requirements": ["Java"]})
	result = validate_evaluation({
		"confidence": 0.9,
		"hard_requirements": [{"requirement": "Java", "status": "met", "evidence": []}],
		"dimensions": _dimensions(rubric, score=10, evidence=["简历中的项目事实"]),
		"strengths": [],
		"concerns": [],
		"next_questions": [],
		"summary": "",
	}, rubric)

	assert result["hard_requirements"][0]["status"] == "unclear"
	assert result["recommendation"] == "manual_review"
	assert result["evidence_coverage"] == 1


def test_non_finite_model_scores_cannot_turn_into_high_scores():
	rubric = normalize_rubric()
	payload = {
		"confidence": float("nan"),
		"hard_requirements": [],
		"dimensions": _dimensions(rubric, score=float("nan"), evidence=["存在证据但分数非法"]),
		"strengths": [],
		"concerns": [],
		"next_questions": [],
		"summary": "",
	}
	result = validate_evaluation(payload, rubric)
	assert result["total_score"] == 0
	assert result["confidence"] == 0.5
	assert all(item["score"] == 0 for item in result["dimensions"])
	assert math.isfinite(result["confidence"])


def test_infinite_model_scores_are_clamped_to_safe_values():
	rubric = normalize_rubric()
	payload = {
		"confidence": float("inf"),
		"hard_requirements": [],
		"dimensions": _dimensions(rubric, score=float("inf"), evidence=["存在证据但分数非法"]),
		"strengths": [],
		"concerns": [],
		"next_questions": [],
		"summary": "",
	}
	result = validate_evaluation(payload, rubric)
	assert result["total_score"] == 0
	assert result["confidence"] == 0.5
