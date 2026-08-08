import json

import pytest

from boss_agent_cli.recruiter_ai import RecruiterAIError, RecruiterAIStore, normalize_rubric


def _evaluation(score: int):
	return {
		"total_score": score,
		"recommendation": "interview",
		"confidence": 0.8,
		"dimensions": [],
		"strengths": [],
		"concerns": [],
		"next_questions": [],
		"summary": f"score {score}",
	}


def test_corrupt_latest_evaluation_never_falls_back_to_older_score(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="JD", rubric=rubric)
	older = store.save_evaluation(
		job_key="java", jd_text="JD",
		resume={"basic": {"name": "A"}, "raw_text": "v1"},
		evaluation=_evaluation(70), source={"type": "zhipin", "geek_id": "g1"}, rubric=rubric,
	)
	newer = store.save_evaluation(
		job_key="java", jd_text="JD",
		resume={"basic": {"name": "A"}, "raw_text": "v2"},
		evaluation=_evaluation(90), source={"type": "zhipin", "geek_id": "g1"}, rubric=rubric,
	)
	(store.evaluations_dir / f"{newer['id']}.json").write_text("{not-json", encoding="utf-8")

	with pytest.raises(RecruiterAIError, match="评估文件损坏"):
		store.rank(job_key="java", top=10)
	with pytest.raises(RecruiterAIError, match="评估文件损坏"):
		store.find_unchanged(
			job_key="java",
			resume={"basic": {"name": "A"}, "raw_text": "v1"},
			source={"type": "zhipin", "geek_id": "g1"},
			rubric=rubric,
		)
	assert (store.evaluations_dir / f"{older['id']}.json").is_file()


def test_evaluation_file_id_mismatch_is_rejected(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	record = store.save_evaluation(
		job_key="java", jd_text="JD", resume={"basic": {"name": "A"}},
		evaluation=_evaluation(80), source={"type": "zhipin", "geek_id": "g1"}, rubric=rubric,
	)
	path = store.evaluations_dir / f"{record['id']}.json"
	payload = json.loads(path.read_text(encoding="utf-8"))
	payload["id"] = "eval_wrong"
	path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

	with pytest.raises(RecruiterAIError, match="标识不一致"):
		store.get_evaluation(record["id"])
	with pytest.raises(RecruiterAIError, match="标识不一致"):
		store.list_evaluations(job_key="java")


def test_integrity_wrapper_preserves_legacy_contact_hydration(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	record = store.save_evaluation(
		job_key="java", jd_text="JD",
		resume={"basic": {"name": "A"}, "phone": "13800000000", "wechat": "abc_12345"},
		evaluation=_evaluation(80), rubric=rubric,
	)
	path = store.evaluations_dir / f"{record['id']}.json"
	payload = json.loads(path.read_text(encoding="utf-8"))
	payload.pop("contacts", None)
	path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

	hydrated = store.get_evaluation(record["id"])
	assert hydrated["contacts"]["phone"] == ["13800000000"]
	assert "abc_12345" in hydrated["contacts"]["wechat"]
