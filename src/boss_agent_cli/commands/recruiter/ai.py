"""Recruiter AI command group."""

import click

from boss_agent_cli.commands.recruiter import ai_autopilot as _autopilot_module
from boss_agent_cli.commands.recruiter.ai_autopilot import autopilot_cmd
from boss_agent_cli.commands.recruiter.ai_autopilot_freshness import install_autopilot_freshness
from boss_agent_cli.commands.recruiter.ai_autopilot_lease import install_autopilot_command_lease
from boss_agent_cli.commands.recruiter.ai_local import (
	batch_cmd,
	configure_cmd,
	evaluate_cmd,
	jobs_cmd,
	mark_cmd,
	rank_cmd,
	reply_cmd,
	report_cmd,
	screen_cmd,
)
from boss_agent_cli.commands.recruiter.ai_platform import (
	evaluate_geek_cmd,
	screen_applications_cmd,
)
from boss_agent_cli.commands.recruiter.ai_read_safety import install_read_error_guard
from boss_agent_cli.commands.recruiter.ai_reply_freshness import install_reply_freshness

install_read_error_guard(rank_cmd)
install_read_error_guard(report_cmd)
install_reply_freshness(reply_cmd)
install_autopilot_freshness(_autopilot_module)
install_autopilot_command_lease(autopilot_cmd)


@click.group("ai", help="招聘者 AI 岗位配置、简历筛选、排序和回复草稿")
def ai_group() -> None:
	"""招聘者 AI 工作台。"""


for command in (
	configure_cmd,
	jobs_cmd,
	evaluate_cmd,
	evaluate_geek_cmd,
	screen_cmd,
	screen_applications_cmd,
	autopilot_cmd,
	batch_cmd,
	rank_cmd,
	report_cmd,
	mark_cmd,
	reply_cmd,
):
	ai_group.add_command(command)
