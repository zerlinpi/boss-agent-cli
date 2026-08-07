from pathlib import Path

from boss_agent_cli.recruiter_ai import candidate_key


def test_local_file_candidate_identity_is_stable_when_resume_content_changes(tmp_path: Path) -> None:
	path = tmp_path / "candidate.json"
	first = {"basic": {"name": "候选人A"}, "raw_text": "Java 5 years"}
	updated = {"basic": {"name": "候选人A"}, "raw_text": "Java 6 years, Spring Cloud"}

	first_key = candidate_key(first, {"type": "local", "path": str(path)})
	updated_key = candidate_key(updated, {"type": "local", "path": str(path)})

	assert first_key == updated_key
	assert first_key.startswith("local-path:")


def test_different_local_files_do_not_merge_even_with_identical_resume_content(tmp_path: Path) -> None:
	resume = {"basic": {"name": "候选人A"}, "raw_text": "Java"}

	first_key = candidate_key(resume, {"type": "local", "path": str(tmp_path / "a.json")})
	second_key = candidate_key(resume, {"type": "local", "path": str(tmp_path / "b.json")})

	assert first_key != second_key


def test_windows_source_path_is_portable_and_case_insensitive() -> None:
	resume = {"basic": {"name": "候选人A"}}
	first = candidate_key(resume, {"type": "local", "path": r"C:\\Resumes\\Candidate.JSON"})
	second = candidate_key(resume, {"type": "local", "path": "c:/resumes/candidate.json"})

	assert first == second


def test_boss_identity_prefers_geek_id_over_friend_id() -> None:
	resume = {"basic": {"name": "候选人A"}}
	first = candidate_key(
		resume,
		{"type": "zhipin", "geek_id": "geek-1", "friend_id": 100},
	)
	second = candidate_key(
		resume,
		{"type": "zhipin", "geek_id": "geek-1", "friend_id": 999},
	)

	assert first == second == "zhipin:geek_id:geek-1"


def test_inline_candidate_identity_keeps_content_based_fallback() -> None:
	first = candidate_key({"basic": {"name": "A"}, "raw_text": "Java"}, {"type": "local"})
	second = candidate_key({"basic": {"name": "A"}, "raw_text": "Python"}, {"type": "local"})

	assert first != second
	assert first.startswith("local:")
