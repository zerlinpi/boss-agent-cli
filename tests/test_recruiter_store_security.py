import pytest

from boss_agent_cli.recruiter_ai import RecruiterAIError, RecruiterAIStore


def test_job_key_rejects_path_traversal(tmp_path):
	store = RecruiterAIStore(tmp_path)
	for key in ("../escape", "..\\escape", ".", ".."):
		with pytest.raises(RecruiterAIError, match="非法路径字符|不能为空"):
			store.save_job(job_key=key, jd_text="Backend engineer")
	assert not (tmp_path / "escape.json").exists()


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
