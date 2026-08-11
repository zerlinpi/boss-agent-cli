from boss_agent_cli.automation.models import CandidateKey, CandidateSnapshot
from boss_agent_cli.automation.scoring import score_candidate


def _candidate(**overrides) -> CandidateSnapshot:
	payload = {
		"key": CandidateKey("candidate"),
		"name": "Candidate",
		"title": "",
		"resume_text": "",
		"city": "",
		"experience_years": None,
		"education": "",
		"last_active_at": "",
		"intent_signals": (),
		"risk_flags": (),
		"do_not_contact": False,
	}
	payload.update(overrides)
	return CandidateSnapshot(**payload)


def test_city_education_and_experience_do_not_change_communication_score() -> None:
	baseline = score_candidate(_candidate())
	credentialed = score_candidate(_candidate(city="北京", education="博士", experience_years=8))
	assert credentialed.score == baseline.score
	assert credentialed.recommendation == baseline.recommendation


def test_explicit_positive_intent_can_reach_continue_conversation() -> None:
	result = score_candidate(_candidate(intent_signals=("有兴趣",), last_active_at="active"))
	assert result.score == 100
	assert result.recommendation == "continue-conversation"


def test_neutral_candidate_stays_below_auto_execute_threshold() -> None:
	result = score_candidate(_candidate(last_active_at="active"))
	assert result.score == 56
	assert result.recommendation == "manual-review"


def test_negative_intent_is_low_readiness() -> None:
	result = score_candidate(_candidate(intent_signals=("暂不考虑",), last_active_at="active"))
	assert result.score == 28
	assert result.recommendation == "manual-review"


def test_risk_flag_forces_manual_review_even_with_positive_intent() -> None:
	result = score_candidate(_candidate(
		intent_signals=("有兴趣",),
		last_active_at="active",
		risk_flags=("privacy",),
	))
	assert result.score == 59
	assert result.recommendation == "manual-review"


def test_do_not_contact_is_hard_block() -> None:
	result = score_candidate(_candidate(
		intent_signals=("有兴趣",),
		last_active_at="active",
		do_not_contact=True,
	))
	assert result.pass_hard_conditions is False
	assert result.score == 0
	assert result.recommendation == "do-not-contact"
	assert "do-not-contact" in result.risk_flags
