import multiprocessing as mp
import os
from pathlib import Path

from boss_agent_cli.automation.runner_lease import AutomationRunnerBusy, runner_lease


def _hold_lease(root: str, ready, release) -> None:
	with runner_lease(Path(root)):
		ready.set()
		release.wait(10)


def _try_lease(root: str, result) -> None:
	try:
		with runner_lease(Path(root)):
			result.put("acquired")
	except AutomationRunnerBusy:
		result.put("busy")


def test_runner_lease_blocks_a_second_process_and_releases_after_exit(tmp_path) -> None:
	ctx = mp.get_context("spawn")
	ready = ctx.Event()
	release = ctx.Event()
	result = ctx.Queue()

	owner = ctx.Process(target=_hold_lease, args=(str(tmp_path), ready, release))
	owner.start()
	try:
		assert ready.wait(10), "owner process did not acquire runner lease"
		contender = ctx.Process(target=_try_lease, args=(str(tmp_path), result))
		contender.start()
		contender.join(10)
		assert contender.exitcode == 0
		assert result.get(timeout=2) == "busy"
	finally:
		release.set()
		owner.join(10)
		if owner.is_alive():
			owner.terminate()
			owner.join(5)

	assert owner.exitcode == 0
	with runner_lease(tmp_path):
		metadata = (tmp_path / ".runner.lock").read_bytes()
		assert metadata
		assert str(os.getpid()).encode() in metadata
