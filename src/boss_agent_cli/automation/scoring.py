"""Communication-readiness scoring for legacy recruiter automation.

This module intentionally does not estimate job suitability. JD-specific candidate
matching belongs to Recruiter Autopilot. The legacy automation score is only a
conservative signal for whether routine communication may continue automatically.
"""

from __future__ import annotations

from boss_agent_cli.automation.models import CandidateSnapshot, MatchScore


def score_candidate(candidate: CandidateSnapshot) -> MatchScore:
	"""Score willingness/readiness to continue communication, not employment fit."""
	risk_flags = set(candidate.risk_flags)
	if candidate.do_not_contact:
		risk_flags.add("do-not-contact")
		return MatchScore(
			pass_hard_conditions=False,
			score=0,
			recommendation="do-not-contact",
			reason="communication blocked: explicit do-not-contact signal",
			risk_flags=tuple(sorted(risk_flags)),
		)

	intent = _intent_score(candidate.intent_signals)
	active = 1.0 if candidate.last_active_at else 0.5
	score = round(intent * 80 + active * 20)

	# Any risk signal requires manual handling even if engagement is otherwise high.
	if risk_flags:
		score = min(score, 59)
		recommendation = "manual-review"
	else:
		recommendation = "continue-conversation" if score >= 70 else "manual-review"

	return MatchScore(
		pass_hard_conditions=True,
		score=score,
		recommendation=recommendation,
		reason=(
			"communication-readiness only; "
			f"intent={intent:.2f}, active={active:.2f}, risk_count={len(risk_flags)}; "
			"job suitability is evaluated separately by JD-specific Recruiter Autopilot"
		),
		risk_flags=tuple(sorted(risk_flags)),
	)


def _intent_score(signals: tuple[str, ...]) -> float:
	"""Map explicit communication intent to a conservative 0..1 readiness value."""
	text = " ".join(signals)
	if any(token in text for token in ("暂不考虑", "不考虑", "观望", "在职不看", "暂时不看")):
		return 0.10
	if any(token in text for token in ("想看机会", "可面试", "近期到岗", "有兴趣")):
		return 1.0
	# No explicit positive intent is intentionally below the human-review threshold,
	# even for a recently active candidate.
	return 0.45
