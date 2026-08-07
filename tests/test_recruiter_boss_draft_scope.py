from pathlib import Path

from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric
from boss_agent_cli.web import RecruiterWebController  # noqa: F401 - installs Web runtime extensions
from boss_agent_cli.web.boss_draft_scope import _DRAFT_SCOPE


def _evaluation(score: int):
	return {
		"total_score": score,
		"confidence": 0.8,
		"recommendation": "interview",
		"dimensions": [],
		"strengths": [],
		"concerns": [],
		"next_questions": [],
		"summary": "",
	}


def test_first_boss_screen_rank_call_only_exposes_new_evaluations(tmp_path: Path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	old = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "历史候选人"}},
		evaluation=_evaluation(99),
		source={"type": "zhipin", "geek_id": "old"},
		rubric=rubric,
	)
	new = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "本轮候选人"}},
		evaluation=_evaluation(70),
		source={"type": "zhipin", "geek_id": "new"},
		rubric=rubric,
	)

	token = _DRAFT_SCOPE.set({
		"job_key": "java",
		"existing_ids": {old["id"]},
		"draft_top": 1,
		"rank_calls": 0,
	})
	try:
		draft_candidates = store.rank(job_key="java", top=50)
		full_ranking = store.rank(job_key="java", top=50)
	finally:
		_DRAFT_SCOPE.reset(token)

	assert [record["id"] for record in draft_candidates] == [new["id"]]
	assert [record["id"] for record in full_ranking] == [old["id"], new["id"]]
