from pathlib import Path

from boss_agent_cli.commands.recruiter import ai_autopilot_job_profile as job_profile
from boss_agent_cli.recruiter_ai import RecruiterAIStore


class FailIfCalled:
	def __getattr__(self, name):
		raise AssertionError(f"unexpected preflight call: {name}")


def test_selected_job_mode_does_not_auto_discover_unrelated_jobs(monkeypatch, tmp_path: Path):
	captured = {}

	def fake_core(**kwargs):
		captured.update(kwargs)
		return {
			"totals": {"jobs_processed": 1},
			"unconfigured_platform_jobs": [],
			"catalog_warning": "",
			"messages_sent": 0,
			"human_review_required": True,
		}

	monkeypatch.setattr(job_profile, "_CORE_RUN_AUTOPILOT", fake_core)
	store = RecruiterAIStore(tmp_path)
	result = job_profile.run_profiled_autopilot(
		data_dir=tmp_path,
		platform=FailIfCalled(),
		service=FailIfCalled(),
		store=store,
		max_pages=1,
		max_candidates_per_job=5,
		refresh_seen_hours=0,
		top=5,
		draft_top=0,
		include_chat=False,
		force=False,
		auto_configure=True,
		selected_job_keys={"manual_job"},
	)
	assert captured["selected_job_keys"] == {"manual_job"}
	assert captured["auto_configure"] is False
	assert result["job_profile_sync"]["selection_scope"] == "explicit_job_keys_no_auto_discovery"
