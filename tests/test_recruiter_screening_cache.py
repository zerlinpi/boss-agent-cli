from pathlib import Path

from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric
from boss_agent_cli.web import RecruiterWebController  # noqa: F401 - installs runtime extensions
from boss_agent_cli.web.screening_cache import screening_cache_scope


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


def test_screening_scope_scans_history_once_and_updates_cache(tmp_path: Path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "A"}},
		evaluation=_evaluation(60),
		source={"type": "zhipin", "geek_id": "g1"},
		rubric=rubric,
	)

	original_list = store.list_evaluations
	calls = 0

	def counted_list(*, job_key=None):
		nonlocal calls
		calls += 1
		return original_list(job_key=job_key)

	store.list_evaluations = counted_list  # type: ignore[method-assign]

	with screening_cache_scope(store, "java"):
		assert calls == 1
		for _ in range(5):
			assert len(store.latest_by_candidate(job_key="java")) == 1
		assert calls == 1

		second = store.save_evaluation(
			job_key="java",
			jd_text="JD",
			resume={"basic": {"name": "B"}},
			evaluation=_evaluation(80),
			source={"type": "zhipin", "geek_id": "g2"},
			rubric=rubric,
		)
		latest = store.latest_by_candidate(job_key="java")
		assert len(latest) == 2
		assert second["id"] in {record["id"] for record in latest.values()}
		assert calls == 1

	store.latest_by_candidate(job_key="java")
	assert calls == 2
