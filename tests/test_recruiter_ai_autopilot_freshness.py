import json
from pathlib import Path

from boss_agent_cli.commands.recruiter import ai_autopilot
from boss_agent_cli.commands.recruiter.ai_autopilot_freshness import install_autopilot_freshness

install_autopilot_freshness(ai_autopilot)


def _write_json(path: Path, payload: dict) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_autopilot_freshness_requires_existing_current_evaluation(tmp_path: Path):
	root = tmp_path / "recruiter-ai"
	job_key = "backend"
	evaluation_id = "eval_abc"
	ledger_key = f"{job_key}:geek_id:g1"
	job_path = root / "jobs" / f"{job_key}.json"
	evaluation_path = root / "evaluations" / f"{evaluation_id}.json"

	_write_json(job_path, {"job_key": job_key, "jd_text": "JD v1", "rubric_fingerprint": "rubric-v1"})
	_write_json(
		evaluation_path,
		{
			"id": evaluation_id,
			"job_key": job_key,
			"jd_text": "JD v1",
			"rubric_fingerprint": "rubric-v1",
		},
	)
	state = ai_autopilot.RecruiterAutopilotState(tmp_path)
	state.record_success(ledger_key, evaluation_id=evaluation_id, skipped_unchanged=False)
	assert state.is_fresh(ledger_key, refresh_hours=24) is True

	_write_json(job_path, {"job_key": job_key, "jd_text": "JD v2", "rubric_fingerprint": "rubric-v1"})
	assert state.is_fresh(ledger_key, refresh_hours=24) is False

	_write_json(job_path, {"job_key": job_key, "jd_text": "JD v1", "rubric_fingerprint": "rubric-v1"})
	evaluation_path.unlink()
	assert state.is_fresh(ledger_key, refresh_hours=24) is False


def test_autopilot_job_description_ignores_generic_content_field():
	payload = {
		"unrelated": {"content": "this is a long unrelated page content value that must not become the JD"},
		"job": {"jobDesc": "real JD"},
	}
	assert ai_autopilot.extract_job_description(payload) == "real JD"
