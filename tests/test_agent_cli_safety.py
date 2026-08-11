import json

import click
from click.testing import CliRunner

from boss_agent_cli.automation.storage import AutomationStorageError
from boss_agent_cli.commands.agent_safety import install_agent_command_safety


def _command(exc: Exception) -> click.Command:
	@click.command("unsafe")
	def command() -> None:
		raise exc

	install_agent_command_safety(command)
	return command


def test_invalid_automation_config_uses_structured_error_envelope() -> None:
	result = CliRunner().invoke(_command(ValueError("bad threshold")))
	assert result.exit_code == 1
	payload = json.loads(result.output)
	assert payload["ok"] is False
	assert payload["error"]["code"] == "INVALID_AUTOMATION_CONFIG"
	assert "bad threshold" in payload["error"]["message"]


def test_corrupt_automation_state_uses_structured_error_envelope() -> None:
	result = CliRunner().invoke(_command(AutomationStorageError("state corrupt")))
	assert result.exit_code == 1
	payload = json.loads(result.output)
	assert payload["ok"] is False
	assert payload["error"]["code"] == "AUTOMATION_STATE_CORRUPT"
	assert "state corrupt" in payload["error"]["message"]
