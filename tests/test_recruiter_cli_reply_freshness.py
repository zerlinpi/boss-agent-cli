import json

from click.testing import CliRunner

from boss_agent_cli.commands.recruiter.ai import reply_cmd
from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric


def _evaluation(score: int = 80):
	return {
		"total_score": score,
		"recommendation": "interview",
		"confidence": 0.8,
		"dimensions": [],
		"strengths": [],
		"concerns": [],
		"next_questions": [],
		"summary": "岗位匹配",
	}


def _invoke_reply(tmp_path, evaluation_id: str):
	return CliRunner().invoke(
		reply_cmd,
		["--evaluation-id", evaluation_id, "--intent", "auto"],
		obj={"data_dir": tmp_path, "json_output": True, "platform": "zhipin"},
	)


def test_cli_reply_rejects_old_job_evaluation_before_ai_configuration(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="旧 JD", rubric=rubric)
	record = store.save_evaluation(
		job_key="java",
		jd_text="旧 JD",
		resume={"basic": {"name": "A"}},
		evaluation=_evaluation(),
		source={"type": "zhipin", "geek_id": "g1"},
		rubric=rubric,
	)
	store.save_job(job_key="java", jd_text="新 JD", rubric=rubric)

	result = _invoke_reply(tmp_path, record["id"])
	assert result.exit_code == 1
	payload = json.loads(result.output)
	assert payload["error"]["code"] == "INVALID_PARAM"
	assert "旧 JD" in payload["error"]["message"]
	assert "AI 服务未配置" not in result.output


def test_cli_reply_rejects_superseded_evaluation_before_ai_configuration(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="JD", rubric=rubric)
	old = store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "A"}, "raw_text": "v1"},
		evaluation=_evaluation(70),
		source={"type": "zhipin", "geek_id": "g1"},
		rubric=rubric,
	)
	store.save_evaluation(
		job_key="java",
		jd_text="JD",
		resume={"basic": {"name": "A"}, "raw_text": "v2"},
		evaluation=_evaluation(85),
		source={"type": "zhipin", "geek_id": "g1"},
		rubric=rubric,
	)

	result = _invoke_reply(tmp_path, old["id"])
	assert result.exit_code == 1
	payload = json.loads(result.output)
	assert payload["error"]["code"] == "INVALID_PARAM"
	assert "更新的评估版本" in payload["error"]["message"]
	assert "AI 服务未配置" not in result.output
