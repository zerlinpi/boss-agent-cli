"""Local graphical recruiter console."""

from boss_agent_cli.web import controller as _controller
from boss_agent_cli.web import tasks as _tasks
from boss_agent_cli.web.autopilot_extension import (
	install_autopilot_controller,
	install_autopilot_server,
	install_autopilot_task_safety,
)
from boss_agent_cli.web.boss_draft_scope import install_boss_draft_scope
from boss_agent_cli.web.candidate_freshness import install_candidate_freshness
from boss_agent_cli.web.config_persistence import install_web_config_persistence
from boss_agent_cli.web.contact_extension import install_contact_assets
from boss_agent_cli.web.container_auth import install_container_auth_guard
from boss_agent_cli.web.controller import RecruiterWebController, WebConsoleError
from boss_agent_cli.web.current_job_results import (
	install_current_job_result_assets,
	install_current_job_results,
)
from boss_agent_cli.web.deletion_serialization import install_deletion_serialization
from boss_agent_cli.web.export_security import install_export_security
from boss_agent_cli.web.http_input_safety import install_http_input_safety
from boss_agent_cli.web.integrity import install_web_integrity
from boss_agent_cli.web.job_analysis_safety import install_job_analysis_safety
from boss_agent_cli.web.lifecycle import install_controller_extensions, install_server_extensions
from boss_agent_cli.web.reliability import install_controller_reliability, install_server_reliability
from boss_agent_cli.web.reply_extension import install_reply_assets
from boss_agent_cli.web.reply_ordering import install_reply_ordering
from boss_agent_cli.web.screening_cache import install_screening_cache
from boss_agent_cli.web.task_controls import install_task_control_server, install_task_manager_controls
from boss_agent_cli.web.task_result_safety import install_task_result_safety
from boss_agent_cli.web.ui_extension import install_ui_reliability_assets
from boss_agent_cli.web.upload_identity import install_web_upload_identity
from boss_agent_cli.web.upload_policy import install_upload_policy
from boss_agent_cli.web.write_input_safety import (
	install_controller_write_input_safety,
	install_write_input_safety,
)

install_export_security(_controller)
install_controller_extensions()
install_web_upload_identity()
install_container_auth_guard()
install_web_config_persistence()
install_controller_reliability()
install_reply_ordering()
install_controller_write_input_safety()
install_candidate_freshness()
install_job_analysis_safety()
install_screening_cache()
install_current_job_results()
install_upload_policy()
install_boss_draft_scope()
install_autopilot_controller()
install_task_manager_controls(_tasks)
install_task_result_safety(_tasks)
install_autopilot_task_safety(_tasks)

from boss_agent_cli.web import server as _server  # noqa: E402

install_server_extensions(_server)
install_deletion_serialization(_server)
install_server_reliability(_server)
install_http_input_safety(_server)
install_write_input_safety(_server)
install_web_integrity(_server)
install_reply_assets(_server)
install_contact_assets(_server)
install_ui_reliability_assets(_server)
install_current_job_result_assets(_server)
install_task_control_server(_server)
install_autopilot_server(_server)
build_server = _server.build_server
main = _server.main

__all__ = ["RecruiterWebController", "WebConsoleError", "build_server", "main"]
