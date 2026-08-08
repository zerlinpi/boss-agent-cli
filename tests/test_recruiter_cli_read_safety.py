import json
import os

from click.testing import CliRunner

from boss_agent_cli.commands.recruiter.ai import rank_cmd, report_cmd
from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric


def _corrupt_saved_job(tmp_path) -> None:
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="JD", rubric=rubric)
	store.save_evaluation(
		job_key="java", jd_text="JD", resume={"basic": {"name": "A"}},
		evaluation={"total_score": 80, "recommendation": "interview", "confidence": 0.8},
		source={"type": "zhipin", "geek_id": "g1"}, rubric=rubric,
	)
	path = store.jobs_dir / "java.json"
	before = path.stat().st_mtime_ns
	path.write_text("{not-json", encoding="utf-8")
	os.utime(path, ns=(before + 2_000_000_000, before + 2_000_000_000))


def _invoke(command, tmp_path):
	return CliRunner().invoke(
		command,
		["--job-key", "java"],
		obj={"data_dir": tmp_path, "json_output": True, "platform": "zhipin"},
	)


def test_rank_returns_structured_error_for_corrupt_saved_job(tmp_path) -> None:
	_corrupt_saved_job(tmp_path)
	result = _invoke(rank_cmd, tmp_path)
	assert result.exit_code == 1
	payload = json.loads(result.output)
	assert payload["error"]["code"] == "INVALID_PARAM"
	assert "岗位配置损坏" in payload["error"]["message"]
	assert "Traceback" not in result.output


def test_report_returns_structured_error_for_corrupt_saved_job(tmp_path) -> None:
	_corrupt_saved_job(tmp_path)
	result = _invoke(report_cmd, tmp_path)
	assert result.exit_code == 1
	payload = json.loads(result.output)
	assert payload["error"]["code"] == "INVALID_PARAM"
	assert "岗位配置损坏" in payload["error"]["message"]
	assert "Traceback" not in result.output
