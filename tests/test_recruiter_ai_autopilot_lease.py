from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from boss_agent_cli.commands.recruiter.ai_autopilot_lease import (
	RecruiterAutopilotBusy,
	recruiter_autopilot_lease,
)


def _wait_for(path: Path, timeout: float = 5.0) -> None:
	deadline = time.time() + timeout
	while time.time() < deadline:
		if path.exists():
			return
		time.sleep(0.02)
	raise AssertionError(f"timed out waiting for {path}")


def test_recruiter_autopilot_lease_blocks_second_process(tmp_path: Path):
	ready = tmp_path / "ready"
	release = tmp_path / "release"
	script = """
import sys, time
from pathlib import Path
from boss_agent_cli.commands.recruiter.ai_autopilot_lease import recruiter_autopilot_lease

data_dir, ready, release = map(Path, sys.argv[1:4])
with recruiter_autopilot_lease(data_dir):
    ready.write_text('ready', encoding='utf-8')
    deadline = time.time() + 10
    while time.time() < deadline and not release.exists():
        time.sleep(0.02)
"""
	env = dict(os.environ)
	root = Path(__file__).resolve().parents[1]
	existing_pythonpath = env.get("PYTHONPATH", "")
	env["PYTHONPATH"] = str(root / "src") + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
	process = subprocess.Popen(
		[sys.executable, "-c", script, str(tmp_path), str(ready), str(release)],
		env=env,
	)
	try:
		_wait_for(ready)
		with pytest.raises(RecruiterAutopilotBusy):
			with recruiter_autopilot_lease(tmp_path):
				pass
	finally:
		release.write_text("release", encoding="utf-8")
		process.wait(timeout=5)
	assert process.returncode == 0


def test_recruiter_autopilot_lease_releases_after_owner_exits(tmp_path: Path):
	with recruiter_autopilot_lease(tmp_path):
		pass
	with recruiter_autopilot_lease(tmp_path):
		pass
