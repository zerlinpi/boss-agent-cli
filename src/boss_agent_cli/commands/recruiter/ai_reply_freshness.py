"""Preflight freshness guard for recruiter AI reply CLI commands."""

from __future__ import annotations

from typing import Any

import click

from boss_agent_cli.commands.recruiter.ai_common import emit_input_error
from boss_agent_cli.recruiter_ai import RecruiterAIError, RecruiterAIStore
from boss_agent_cli.recruiter_evaluation_freshness import require_current_evaluation


def install_reply_freshness(command: click.Command) -> None:
	"""Reject stale evaluation IDs before the reply command resolves AI configuration."""
	if getattr(command, "_boss_reply_freshness_installed", False):
		return
	original = command.callback
	if original is None:
		return

	@click.pass_context
	def guarded(ctx: click.Context, *args: Any, **kwargs: Any) -> Any:
		evaluation_id = str(kwargs.get("evaluation_id") or "").strip()
		if evaluation_id:
			store = RecruiterAIStore(ctx.obj["data_dir"])
			try:
				record = store.get_evaluation(evaluation_id)
				require_current_evaluation(store, record)
			except RecruiterAIError as exc:
				emit_input_error(ctx, str(exc))
				return None
		return original(*args, **kwargs)

	command.callback = guarded
	setattr(command, "_boss_reply_freshness_installed", True)
