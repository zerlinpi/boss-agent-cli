"""Structured CLI error mapping for AI configuration validation."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

import click

from boss_agent_cli.display import handle_error_output


def install_ai_config_command_safety(command: click.Command) -> None:
	"""Convert persistence validation errors into the normal CLI error envelope."""
	if getattr(command, "_boss_ai_config_safety_installed", False):
		return
	callback = command.callback
	if callback is None:
		return
	original: Callable[..., Any] = callback

	@wraps(original)
	def safe_callback(*args: Any, **kwargs: Any) -> Any:
		try:
			return original(*args, **kwargs)
		except ValueError as exc:
			ctx = click.get_current_context(silent=True)
			if ctx is None:
				raise
			handle_error_output(
				ctx,
				"ai-config",
				code="INVALID_AI_CONFIG",
				message=str(exc),
				recoverable=True,
				recovery_action="修正 provider/model/base-url/temperature/max-tokens/API key 后重新执行 boss ai config",
			)
			ctx.exit(1)
			return None

	command.callback = safe_callback
	setattr(command, "_boss_ai_config_safety_installed", True)
