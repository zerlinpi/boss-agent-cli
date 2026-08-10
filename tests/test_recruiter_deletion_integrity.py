import pytest

from boss_agent_cli.recruiter_ai import RecruiterAIError, RecruiterAIStore, normalize_rubric
from boss_agent_cli.web.deletion import delete_candidate_data, delete_job_data


def _records(tmp_path):
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="Java engineer", rubric=rubric)
	evaluation = store.save_evaluation(
		job_key="java",
		jd_text="Java engineer",
		resume={"basic": {"name": "Candidate"}, "raw_text": "Java backend engineer"},
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		source={"type": "local", "path": "candidate.json"},
		rubric=rubric,
	)
	reply = store.save_reply(
		evaluation_id=evaluation["id"],
		intent="acknowledge",
		conversation="",
		draft={"reply": "收到。"},
	)
	return store, evaluation, reply


def test_candidate_deletion_fails_before_mutation_when_any_evaluation_is_corrupt(tmp_path) -> None:
	store, evaluation, reply = _records(tmp_path)
	(store.evaluations_dir / "eval_broken.json").write_text("{not-json", encoding="utf-8")

	with pytest.raises(RecruiterAIError, match="无法确认完整删除范围"):
		delete_candidate_data(store, evaluation["id"])

	assert (store.evaluations_dir / f"{evaluation['id']}.json").exists()
	assert (store.replies_dir / f"{reply['id']}.json").exists()


def test_job_deletion_fails_before_mutation_when_any_reply_is_corrupt(tmp_path) -> None:
	store, evaluation, reply = _records(tmp_path)
	(store.replies_dir / "reply_broken.json").write_text("{not-json", encoding="utf-8")

	with pytest.raises(RecruiterAIError, match="无法确认完整删除范围"):
		delete_job_data(store, "java")

	assert (store.jobs_dir / "java.json").exists()
	assert (store.evaluations_dir / f"{evaluation['id']}.json").exists()
	assert (store.replies_dir / f"{reply['id']}.json").exists()
