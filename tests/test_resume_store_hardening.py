import os
import stat

import pytest

from boss_agent_cli.resume.models import ResumeData
from boss_agent_cli.resume.store import ResumeStore


def test_non_object_resume_json_does_not_break_listing_or_get(tmp_path) -> None:
	store = ResumeStore(tmp_path / "resumes")
	(store._dir / "broken.json").write_text('["unexpected"]', encoding="utf-8")

	assert store.list_all() == []
	assert store.get("broken") is None


def test_resume_save_uses_owner_only_permissions_on_posix(tmp_path) -> None:
	store = ResumeStore(tmp_path / "resumes")
	store.save(ResumeData(name="Candidate", title="Engineer"))
	path = store._path_for("Candidate")

	if os.name != "nt":
		assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_resume_import_requires_object_payload(tmp_path) -> None:
	store = ResumeStore(tmp_path / "resumes")
	path = tmp_path / "resume.json"
	path.write_text('["unexpected"]', encoding="utf-8")

	with pytest.raises(ValueError, match="顶层必须是对象"):
		store.import_file(path)


def test_resume_import_requires_object_envelope_data(tmp_path) -> None:
	store = ResumeStore(tmp_path / "resumes")
	path = tmp_path / "resume.json"
	path.write_text('{"version":"1.0","data":[]}', encoding="utf-8")

	with pytest.raises(ValueError, match="envelope.data"):
		store.import_file(path)
