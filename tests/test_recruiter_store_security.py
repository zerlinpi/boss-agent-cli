import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from boss_agent_cli.recruiter_ai import RecruiterAIError, RecruiterAIStore, normalize_rubric


def test_job_key_rejects_path_traversal(tmp_path):
	store = RecruiterAIStore(tmp_path)
	for key in ("../escape", "..\\escape", ".", ".."):
		with pytest.raises(RecruiterAIError, match="非法路径字符|不能为空"):
			store.save_job(job_key=key, jd_text="Backend engineer")
	assert not (tmp_path / "escape.json").exists()


def test_job_key_rejects_windows_reserved_or_invalid_names(tmp_path):
	store = RecruiterAIStore(tmp_path)
	for key in ("CON", "nul", "COM1", "LPT9.txt", "bad:name", "trailing."):
		with pytest.raises(RecruiterAIError, match="Windows 保留文件名|非法路径字符"):
			store.save_job(job_key=key, jd_text="Backend engineer")


def test_evaluation_id_rejects_path_traversal(tmp_path):
	store = RecruiterAIStore(tmp_path)
	for record_id in ("../config", "..\\config"):
		with pytest.raises(RecruiterAIError, match="非法路径字符"):
			store.get_evaluation(record_id)


def test_corrupt_job_record_uses_recruiter_error_contract(tmp_path):
	store = RecruiterAIStore(tmp_path)
	(store.jobs_dir / "broken.json").write_text("{not-json", encoding="utf-8")
	with pytest.raises(RecruiterAIError, match="岗位配置损坏"):
		store.get_job("broken")


def test_corrupt_evaluation_record_uses_recruiter_error_contract(tmp_path):
	store = RecruiterAIStore(tmp_path)
	(store.evaluations_dir / "eval_broken.json").write_text("{not-json", encoding="utf-8")
	with pytest.raises(RecruiterAIError, match="评估记录损坏"):
		store.get_evaluation("eval_broken")


def test_concurrent_job_writes_leave_valid_json_and_no_shared_temp_file(tmp_path):
	store = RecruiterAIStore(tmp_path)

	def write(index: int) -> None:
		store.save_job(job_key="java", jd_text=f"Backend engineer {index}")

	with ThreadPoolExecutor(max_workers=8) as executor:
		list(executor.map(write, range(32)))

	payload = json.loads((store.jobs_dir / "java.json").read_text(encoding="utf-8"))
	assert payload["job_key"] == "java"
	assert not list(store.jobs_dir.glob(".java.json.*.tmp"))


def test_reply_cannot_be_saved_for_missing_evaluation(tmp_path):
	store = RecruiterAIStore(tmp_path)
	with pytest.raises(RecruiterAIError, match="评估记录不存在"):
		store.save_reply(
			evaluation_id="eval_missing",
			intent="acknowledge",
			conversation="",
			draft={"reply": "收到"},
		)
	assert list(store.replies_dir.glob("reply_*.json")) == []


def test_rank_pushes_non_finite_legacy_scores_to_bottom(tmp_path):
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	valid = store.save_evaluation(
		job_key="python",
		jd_text="Python engineer",
		resume={"name": "Valid"},
		evaluation={"total_score": 80, "confidence": 0.8, "recommendation": "interview"},
		source={"type": "test", "candidate_id": "valid"},
		rubric=rubric,
	)
	legacy = store.save_evaluation(
		job_key="python",
		jd_text="Python engineer",
		resume={"name": "Legacy"},
		evaluation={"total_score": float("nan"), "confidence": float("inf"), "recommendation": "interview"},
		source={"type": "test", "candidate_id": "legacy"},
		rubric=rubric,
	)
	ranking = store.rank(job_key="python", top=10)
	assert ranking[0]["id"] == valid["id"]
	assert ranking[-1]["id"] == legacy["id"]


def test_status_note_is_bounded_for_direct_store_callers(tmp_path):
	store = RecruiterAIStore(tmp_path)
	record = store.save_evaluation(
		job_key="python",
		jd_text="Python engineer",
		resume={"name": "Alice"},
		evaluation={"total_score": 70, "confidence": 0.7, "recommendation": "interview"},
		source={"type": "test", "candidate_id": "alice"},
		rubric=normalize_rubric(),
	)
	updated = store.set_status(record["id"], "hold", note="x" * 6000)
	assert len(updated["status_note"]) == 5000
