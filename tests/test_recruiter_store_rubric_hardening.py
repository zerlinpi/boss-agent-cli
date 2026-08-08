import pytest

from boss_agent_cli.recruiter_ai import RecruiterAIError, RecruiterAIStore


def test_store_save_job_uses_hardened_rubric_contract(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	with pytest.raises(RecruiterAIError, match="代理条件"):
		store.save_job(
			job_key="java",
			jd_text="Java 工程师",
			rubric={"title": "90后 Java 工程师"},
		)
	assert not (store.jobs_dir / "java.json").exists()


def test_store_save_evaluation_rejects_canonical_duplicate_dimensions(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	with pytest.raises(RecruiterAIError, match="归一化后不能重复"):
		store.save_evaluation(
			job_key="java",
			jd_text="Java 工程师",
			resume={"basic": {"name": "候选人A"}},
			evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
			rubric={
				"dimensions": [
					{"name": "required_skills", "max_score": 50},
					{"name": "RequiredSkills", "max_score": 50},
				],
			},
		)
	assert list(store.evaluations_dir.glob("eval_*.json")) == []
