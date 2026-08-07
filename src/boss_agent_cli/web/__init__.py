"""Local graphical recruiter console."""

from boss_agent_cli.web.contact_extension import install_contact_assets
from boss_agent_cli.web.controller import RecruiterWebController, WebConsoleError
from boss_agent_cli.web.export_security import install_export_security
from boss_agent_cli.web.lifecycle import install_controller_extensions, install_server_extensions
from boss_agent_cli.web.reply_extension import install_reply_assets

install_export_security(__import__("boss_agent_cli.web.controller", fromlist=["*"]))
install_controller_extensions()

from boss_agent_cli.web import server as _server  # noqa: E402

install_server_extensions(_server)
install_reply_assets(_server)
install_contact_assets(_server)
build_server = _server.build_server
main = _server.main

__all__ = ["RecruiterWebController", "WebConsoleError", "build_server", "main"]
