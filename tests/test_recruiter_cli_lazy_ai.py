import json
from pathlib import Path

from click.testing import CliRunner

from boss_agent_cli.main import cli
from boss_agent_cli.recruiter_ai import RecruiterAIStore, normalize_rubric


def _evaluation(score: int = 70):
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


def _seed_unchanged_candidate(tmp_path: Path):
	resume_dir = tmp_path / "resumes"
	resume_dir.mkdir()
	path = resume_dir / "candidate.json"
	resume = {"basic": {"name": "Alice"}, "raw_text": "Java 5 years"}
	path.write_text(json.dumps(resume), encoding="utf-8")
	store = RecruiterAIStore(tmp_path)
	rubric = normalize_rubric()
	store.save_job(job_key="java", jd_text="Java backend engineer", rubric=rubric)
	store.save_evaluation(
		job_key="java",
		jd_text="Java backend engineer",
		resume=resume,
		evaluation=_evaluation(),
		source={"type": "local", "path": str(path)},
		rubric=rubric,
	)
	return resume_dir, path


def _invoke(tmp_path: Path, args: list[str]):
	return CliRunner().invoke(cli, ["--data-dir", str(tmp_path), "--json", "hr", "ai", *args])


def test_screen_all_unchanged_does_not_require_ai_configuration(tmp_path: Path) -> None:
	resume_dir, _ = _seed_unchanged_candidate(tmp_path)

	result = _invoke(tmp_path, ["screen", "--job-key", "java", "--resume-dir", str(resume_dir)])

	assert result.exit_code == 0, result.output
	payload = json.loads(result.output)
	assert payload["data"]["processed_count"] == 0
	assert payload["data"]["skipped_unchanged_count"] == 1


def test_evaluate_at_file_uses_path_identity_and_skips_without_ai(tmp_path: Path) -> None:
	_, path = _seed_unchanged_candidate(tmp_path)

	result = _invoke(tmp_path, ["evaluate", "--job-key", "java", "--resume", f"@{path}"])

	assert result.exit_code == 0, result.output
	payload = json.loads(result.output)
	assert payload["data"]["skipped"] is True
	assert payload["data"]["skip_reason"] == "unchanged"


def test_changed_resume_without_ai_returns_configuration_error(tmp_path: Path) -> None:
	resume_dir, path = _seed_unchanged_candidate(tmp_path)
	path.write_text(
		json.dumps({"basic": {"name": "Alice"}, "raw_text": "Java 6 years, new project"}),
		encoding="utf-8",
	)

	result = _invoke(tmp_path, ["screen", "--job-key", "java", "--resume-dir", str(resume_dir)])

	assert result.exit_code == 1
	payload = json.loads(result.output)
	assert payload["error"]["code"] == "AI_NOT_CONFIGURED"
