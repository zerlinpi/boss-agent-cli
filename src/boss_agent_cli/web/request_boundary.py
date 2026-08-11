"""Protocol-wide request boundary for the loopback recruiter Web console."""

from __future__ import annotations

from typing import Any, Callable

from boss_agent_cli.web import controller as controller_module
from boss_agent_cli.web.lifecycle import is_loopback_origin

_INSTALLED = False


def install_request_boundary(server_module: Any) -> None:
	"""Validate Host/Origin immediately after parsing, before any HTTP verb handler runs."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	handler_cls = server_module.RecruiterRequestHandler
	original_parse_request: Callable[..., bool] = handler_cls.parse_request

	def parse_request(self: Any) -> bool:
		if not original_parse_request(self):
			return False
		# Base server validation preserves the canonical INVALID_HOST / 421 response.
		if not self._require_loopback_host():
			return False
		if not is_loopback_origin(self.headers.get("Origin", "")):
			self._send_error(controller_module.WebConsoleError(
				"INVALID_LOCAL_ORIGIN",
				"Web 控制台只接受本机回环地址请求",
				status=403,
			))
			return False
		return True

	setattr(handler_cls, "parse_request", parse_request)
