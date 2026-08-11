"""Structured error boundaries for recruiter automation CLI commands."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

import click

from boss_agent_cli.automation.storage import AutomationStorageError
from boss_agent_cli.display import handle_error_output


def install_agent_command_safety(command: click.Command) -> None:
	"""Convert expected automation config/storage failures into normal CLI envelopes."""
	if getattr(command, "_boss_agent_safety_installed", False):
		return
	callback = command.callback
	if callback is None:
		return
	original: Callable[..., Any] = callback

	@wraps(original)
	def safe_callback(*args: Any, **kwargs: Any) -> Any:
		try:
			return original(*args, **kwargs)
		except AutomationStorageError as exc:
			ctx = click.get_current_context(silent=True)
			if ctx is None:
				raise
			handle_error_output(
				ctx,
				f"agent.{command.name or 'command'}",
				code="AUTOMATION_STATE_CORRUPT",
				message=str(exc),
				recoverable=True,
				recovery_action="检查 ~/.boss-agent/automation 下的 state/queue 文件；保留备份后修复损坏记录再重试",
			)
			ctx.exit(1)
			return None
		except ValueError as exc:
			ctx = click.get_current_context(silent=True)
			if ctx is None:
				raise
			handle_error_output(
				ctx,
				f"agent.{command.name or 'command'}",
				code="INVALID_AUTOMATION_CONFIG",
				message=str(exc),
				recoverable=True,
				recovery_action="修正 config.json 中 automation 配置的 mode、阈值、限额和 allowed_actions 后重试",
			)
			ctx.exit(1)
			return None

	command.callback = safe_callback
	setattr(command, "_boss_agent_safety_installed", True)
