"""Local graphical recruiter console."""

from boss_agent_cli.web.controller import RecruiterWebController, WebConsoleError
from boss_agent_cli.web.server import build_server, main

__all__ = ["RecruiterWebController", "WebConsoleError", "build_server", "main"]
