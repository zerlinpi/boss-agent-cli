from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric
from boss_agent_cli.recruiter_evaluation_freshness import evaluation_freshness
from boss_agent_cli.web import RecruiterWebController


def _save_job(store: RecruiterAIStore, job_key: str, jd_text: str, rubric=None):
	return store.save_job(
		job_key=job_key,
		jd_text=jd_text,
		rubric=rubric or normalize_rubric(),
		metadata={"title": job_key},
	)


def _save_eval(store: RecruiterAIStore, job_key: str, jd_text: str, rubric, *, score: int = 80):
	return store.save_evaluation(
		job_key=job_key,
		jd_text=jd_text,
		resume={"basic": {"name": "张三"}, "work_experience": [{"company": "Example"}]},
		evaluation={"total_score": score, "recommendation": "interview", "confidence": 0.8},
		source={"type": "zhipin", "geek_id": "geek-1", "friend_id": 123},
		rubric=rubric,
	)


def test_current_evaluation_reports_current(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	_save_job(store, "java", "Java JD", rubric)
	record = _save_eval(store, "java", "Java JD", rubric)

	freshness = evaluation_freshness(store, record, require_saved_job=True)
	assert freshness["is_current"] is True
	assert freshness["job_current"] is True
	assert freshness["version_current"] is True
	assert freshness["latest_evaluation_id"] == record["id"]


def test_old_jd_evaluation_is_explainably_stale(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	_save_job(store, "java", "Java JD v1", rubric)
	record = _save_eval(store, "java", "Java JD v1", rubric)
	_save_job(store, "java", "Java JD v2", rubric)

	freshness = evaluation_freshness(store, record, require_saved_job=True)
	assert freshness["is_current"] is False
	assert "旧 JD" in freshness["reason"]
	assert freshness["job_current"] is False
	assert freshness["version_current"] is True
	assert freshness["latest_evaluation_id"] == record["id"]


def test_old_job_evaluation_still_points_to_existing_newer_version(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	_save_job(store, "java", "Java JD v1", rubric)
	old = _save_eval(store, "java", "Java JD v1", rubric, score=70)
	_save_job(store, "java", "Java JD v2", rubric)
	latest = _save_eval(store, "java", "Java JD v2", rubric, score=90)

	freshness = evaluation_freshness(store, old, require_saved_job=True)
	assert freshness["is_current"] is False
	assert "旧 JD" in freshness["reason"]
	assert freshness["version_current"] is False
	assert freshness["latest_evaluation_id"] == latest["id"]


def test_old_rubric_evaluation_is_explainably_stale(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric_v1 = normalize_rubric()
	rubric_v2 = normalize_rubric({
		"dimensions": [
			{"name": "required_skills", "max_score": 60},
			{"name": "relevant_experience", "max_score": 40},
		]
	})
	_save_job(store, "java", "Java JD", rubric_v1)
	record = _save_eval(store, "java", "Java JD", rubric_v1)
	_save_job(store, "java", "Java JD", rubric_v2)

	freshness = evaluation_freshness(store, record, require_saved_job=True)
	assert freshness["is_current"] is False
	assert "旧评分规则" in freshness["reason"]
	assert freshness["job_current"] is False


def test_superseded_evaluation_points_to_latest_version(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	_save_job(store, "java", "Java JD", rubric)
	old = _save_eval(store, "java", "Java JD", rubric, score=75)
	latest = _save_eval(store, "java", "Java JD", rubric, score=85)

	freshness = evaluation_freshness(store, old, require_saved_job=True)
	assert freshness["is_current"] is False
	assert "更新的评估版本" in freshness["reason"]
	assert freshness["latest_evaluation_id"] == latest["id"]


def test_web_candidate_detail_includes_freshness_metadata(tmp_path) -> None:
	controller = RecruiterWebController(tmp_path)
	rubric = normalize_rubric()
	controller.store.save_job(
		job_key="java", jd_text="Java JD", rubric=rubric, metadata={"title": "Java"}
	)
	old = _save_eval(controller.store, "java", "Java JD", rubric, score=70)
	latest = _save_eval(controller.store, "java", "Java JD", rubric, score=90)

	old_detail = controller.candidate_detail(old["id"])
	latest_detail = controller.candidate_detail(latest["id"])
	assert old_detail["freshness"]["is_current"] is False
	assert old_detail["freshness"]["latest_evaluation_id"] == latest["id"]
	assert latest_detail["freshness"]["is_current"] is True
