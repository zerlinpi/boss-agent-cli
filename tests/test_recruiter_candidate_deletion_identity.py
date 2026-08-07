from pathlib import Path

from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric
from boss_agent_cli.web.deletion import delete_candidate_data


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


def test_candidate_delete_removes_legacy_and_current_identity_versions(tmp_path: Path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	source = {"type": "local", "path": str(tmp_path / "candidate.json")}
	first = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "候选人A"}, "raw_text": "old resume"},
		evaluation=_evaluation(60),
		source=source,
		rubric=rubric,
	)
	first_path = store.evaluations_dir / f"{first['id']}.json"
	legacy = store.get_evaluation(first["id"])
	legacy["candidate_key"] = "local:legacy-content-key"
	store._write(first_path, legacy)
	store.save_reply(
		evaluation_id=first["id"],
		intent="acknowledge",
		conversation="",
		draft={"reply": "first"},
	)

	second = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "候选人A"}, "raw_text": "updated resume"},
		evaluation=_evaluation(80),
		source=source,
		rubric=rubric,
	)
	store.save_reply(
		evaluation_id=second["id"],
		intent="acknowledge",
		conversation="",
		draft={"reply": "second"},
	)

	result = delete_candidate_data(store, second["id"])

	assert result["evaluation_count"] == 2
	assert result["reply_count"] == 2
	assert store.list_evaluations(job_key="java") == []
	assert list(store.replies_dir.glob("reply_*.json")) == []
