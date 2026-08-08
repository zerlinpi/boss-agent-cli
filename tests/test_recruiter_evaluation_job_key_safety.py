import pytest

from boss_agent_cli.recruiter_ai import RecruiterAIError, RecruiterAIStore, normalize_rubric
from boss_agent_cli.recruiter_evaluation_freshness import get_saved_job_optional


@pytest.mark.parametrize(
	"job_key",
	["../escape", "..\\escape", "/tmp/escape", "C:\\temp\\escape", "nested/path"],
)
def test_direct_store_evaluation_rejects_unsafe_job_keys_before_write(tmp_path, job_key) -> None:
	store = RecruiterAIStore(tmp_path)
	with pytest.raises(RecruiterAIError, match="job_key"):
		store.save_evaluation(
			job_key=job_key,
			jd_text="JD",
			resume={"basic": {"name": "A"}},
			evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
			rubric=normalize_rubric(),
		)
	assert list(store.evaluations_dir.glob("eval_*.json")) == []


def test_freshness_job_lookup_validates_key_before_path_probe(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	with pytest.raises(RecruiterAIError, match="job_key"):
		get_saved_job_optional(store, "../../outside")
