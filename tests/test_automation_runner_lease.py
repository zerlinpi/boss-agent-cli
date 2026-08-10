import pytest

from boss_agent_cli.automation.runner_lease import AutomationRunnerBusy, runner_lease


def test_second_runner_lease_is_rejected_while_first_is_active(tmp_path) -> None:
	with runner_lease(tmp_path):
		with pytest.raises(AutomationRunnerBusy, match="已有 automation runner"):
			with runner_lease(tmp_path):
				pass


def test_runner_lease_can_be_reacquired_after_release(tmp_path) -> None:
	with runner_lease(tmp_path):
		pass
	with runner_lease(tmp_path):
		pass
