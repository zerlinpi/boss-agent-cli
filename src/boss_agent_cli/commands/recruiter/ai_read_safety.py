"""Structured error guards for recruiter AI read commands."""

from __future__ import annotations

from typing import Any

import click

from boss_agent_cli.commands.recruiter.ai_common import emit_input_error
from boss_agent_cli.recruiter_ai import RecruiterAIError


def install_read_error_guard(command: click.Command) -> None:
	"""Turn data/config read failures into the recruiter AI JSON error contract."""
	if getattr(command, "_boss_read_error_guard_installed", False):
		return
	original = command.callback
	if original is None:
		return

	@click.pass_context
	def guarded(ctx: click.Context, *args: Any, **kwargs: Any) -> Any:
		try:
			return original(*args, **kwargs)
		except RecruiterAIError as exc:
			emit_input_error(ctx, str(exc))
			return None

	command.callback = guarded
	setattr(command, "_boss_read_error_guard_installed", True)
