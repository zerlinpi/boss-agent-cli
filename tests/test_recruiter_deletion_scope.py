import pytest

from boss_agent_cli.recruiter_ai import RecruiterAIError, RecruiterAIStore, normalize_rubric
from boss_agent_cli.web.deletion import delete_candidate_data


def _save_candidate(store: RecruiterAIStore, job_key: str):
	return store.save_evaluation(
		job_key=job_key,
		jd_text=f"{job_key} JD",
		resume={"basic": {"name": "张三"}, "work_experience": [{"company": "Example"}]},
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		source={"type": "zhipin", "geek_id": "geek-1", "friend_id": 123},
		rubric=normalize_rubric(),
	)


def test_delete_candidate_only_removes_versions_and_replies_in_target_job(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	job_a = _save_candidate(store, "java")
	job_a_v2 = _save_candidate(store, "java")
	job_b = _save_candidate(store, "python")

	for record in (job_a, job_a_v2, job_b):
		store.save_reply(
			evaluation_id=record["id"],
			intent="acknowledge",
			conversation="收到",
			draft={"reply": "已收到"},
		)

	result = delete_candidate_data(store, job_a_v2["id"])
	assert result["job_key"] == "java"
	assert result["evaluation_count"] == 2
	assert result["reply_count"] == 2

	with pytest.raises(RecruiterAIError):
		store.get_evaluation(job_a["id"])
	with pytest.raises(RecruiterAIError):
		store.get_evaluation(job_a_v2["id"])

	assert store.get_evaluation(job_b["id"])["job_key"] == "python"
	remaining_reply_ids = {item["evaluation_id"] for item in store.list_replies(limit=20)} if hasattr(store, "list_replies") else {
		path.read_text(encoding="utf-8") for path in store.replies_dir.glob("reply_*.json")
	}
	if hasattr(store, "list_replies"):
		assert job_b["id"] in remaining_reply_ids
	else:
		assert any(job_b["id"] in item for item in remaining_reply_ids)
