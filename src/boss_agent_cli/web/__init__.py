"""Local graphical recruiter console."""

from boss_agent_cli.web.controller import RecruiterWebController, WebConsoleError
from boss_agent_cli.web.lifecycle import install_controller_extensions, install_server_extensions

install_controller_extensions()

from boss_agent_cli.web import server as _server  # noqa: E402

install_server_extensions(_server)
build_server = _server.build_server
main = _server.main

__all__ = ["RecruiterWebController", "WebConsoleError", "build_server", "main"]
