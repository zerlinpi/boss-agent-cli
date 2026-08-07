"""Local graphical recruiter console."""

from boss_agent_cli.web import controller as _controller
from boss_agent_cli.web import tasks as _tasks
from boss_agent_cli.web.boss_draft_scope import install_boss_draft_scope
from boss_agent_cli.web.contact_extension import install_contact_assets
from boss_agent_cli.web.controller import RecruiterWebController, WebConsoleError
from boss_agent_cli.web.export_security import install_export_security
from boss_agent_cli.web.lifecycle import install_controller_extensions, install_server_extensions
from boss_agent_cli.web.reliability import install_controller_reliability, install_server_reliability
from boss_agent_cli.web.reply_extension import install_reply_assets
from boss_agent_cli.web.screening_cache import install_screening_cache
from boss_agent_cli.web.task_controls import install_task_control_server, install_task_manager_controls
from boss_agent_cli.web.ui_extension import install_ui_reliability_assets
from boss_agent_cli.web.upload_policy import install_upload_policy

install_export_security(_controller)
install_controller_extensions()
install_controller_reliability()
install_screening_cache()
install_upload_policy()
install_boss_draft_scope()
install_task_manager_controls(_tasks)

from boss_agent_cli.web import server as _server  # noqa: E402

install_server_extensions(_server)
install_server_reliability(_server)
install_reply_assets(_server)
install_contact_assets(_server)
install_ui_reliability_assets(_server)
install_task_control_server(_server)
build_server = _server.build_server
main = _server.main

__all__ = ["RecruiterWebController", "WebConsoleError", "build_server", "main"]
