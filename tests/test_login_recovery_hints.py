import click

from boss_agent_cli.commands.login import _classify_login_error


def _context() -> click.Context:
	return click.Context(click.Command("login"), obj={"platform": "zhipin", "role": "candidate"})


def test_cdp_recovery_hints_do_not_reference_nonexistent_command() -> None:
	payload = _classify_login_error(ConnectionError("CDP unavailable"), _context())
	actions = payload["hints"]["next_actions"]

	assert all("boss-chrome" not in action for action in actions)
	assert any("--cdp-url" in action for action in actions)
	assert any("去掉 --cdp" in action for action in actions)


def test_timeout_recovery_hints_use_real_cdp_configuration() -> None:
	payload = _classify_login_error(TimeoutError("登录超时"), _context())
	actions = payload["hints"]["next_actions"]

	assert all("boss-chrome" not in action for action in actions)
	assert any("--cdp-url" in action for action in actions)
