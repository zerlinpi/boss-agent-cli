from pathlib import Path

from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric
from boss_agent_cli.web import RecruiterWebController  # installs runtime extensions
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


def test_nested_scope_loads_each_distinct_job_only_once(tmp_path: Path) -> None:
	store = RecruiterAIStore(tmp_path)
	original_list = store.list_evaluations
	calls: list[str | None] = []

	def counted_list(*, job_key=None):
		calls.append(job_key)
		return original_list(job_key=job_key)

	store.list_evaluations = counted_list  # type: ignore[method-assign]
	with screening_cache_scope(store, "java"):
		with screening_cache_scope(store, "python"):
			store.latest_by_candidate(job_key="java")
			store.latest_by_candidate(job_key="python")
			store.latest_by_candidate(job_key="python")

	assert calls == ["java", "python"]


def test_candidates_composite_read_scans_history_once(tmp_path: Path) -> None:
	controller = RecruiterWebController(tmp_path)
	rubric = normalize_rubric()
	controller.store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "A"}},
		evaluation=_evaluation(80),
		source={"type": "zhipin", "geek_id": "g1"},
		rubric=rubric,
	)
	original_list = controller.store.list_evaluations
	calls = 0

	def counted_list(*, job_key=None):
		nonlocal calls
		calls += 1
		return original_list(job_key=job_key)

	controller.store.list_evaluations = counted_list  # type: ignore[method-assign]
	result = controller.candidates("java", top=20)

	assert result["items"][0]["candidate_name"] == "A"
	assert result["report"]["total_candidates"] == 1
	assert result["analytics"]["total"] == 1
	assert calls == 1


def test_bootstrap_scans_evaluation_directory_once_for_multiple_jobs(tmp_path: Path, monkeypatch) -> None:
	controller = RecruiterWebController(tmp_path)
	rubric = normalize_rubric()
	controller.store.save_job(job_key="java", jd_text="Java JD", rubric=rubric)
	controller.store.save_job(job_key="python", jd_text="Python JD", rubric=rubric)
	controller.store.save_evaluation(
		job_key="java",
		jd_text="Java JD",
		resume={"basic": {"name": "A"}},
		evaluation=_evaluation(80),
		source={"type": "zhipin", "geek_id": "g1"},
		rubric=rubric,
	)
	controller.auth_status = lambda: {"logged_in": False, "state": "missing", "summary": "", "health": {}}  # type: ignore[method-assign]

	original_glob = Path.glob
	evaluation_scans = 0

	def counted_glob(path: Path, pattern: str):
		nonlocal evaluation_scans
		if path == controller.store.evaluations_dir and pattern == "eval_*.json":
			evaluation_scans += 1
		return original_glob(path, pattern)

	monkeypatch.setattr(Path, "glob", counted_glob)
	result = controller.bootstrap()

	assert result["onboarding"]["has_candidates"] is True
	assert evaluation_scans == 1


def test_bootstrap_with_no_jobs_does_not_scan_evaluations(tmp_path: Path, monkeypatch) -> None:
	controller = RecruiterWebController(tmp_path)
	controller.auth_status = lambda: {"logged_in": False, "state": "missing", "summary": "", "health": {}}  # type: ignore[method-assign]
	original_glob = Path.glob
	evaluation_scans = 0

	def counted_glob(path: Path, pattern: str):
		nonlocal evaluation_scans
		if path == controller.store.evaluations_dir and pattern == "eval_*.json":
			evaluation_scans += 1
		return original_glob(path, pattern)

	monkeypatch.setattr(Path, "glob", counted_glob)
	result = controller.bootstrap()

	assert result["onboarding"]["has_candidates"] is False
	assert evaluation_scans == 0
