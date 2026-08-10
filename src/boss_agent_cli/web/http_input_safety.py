"""HTTP request-boundary hardening for the local recruiter Web server."""

from __future__ import annotations

from typing import Any, Callable

from boss_agent_cli.web import controller as controller_module

_INSTALLED = False


def install_http_input_safety(server_module: Any) -> None:
	"""Reject protocol-invalid negative Content-Length values before body parsing."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	handler_cls = server_module.RecruiterRequestHandler
	original_read: Callable[..., dict[str, Any]] = handler_cls._read_json

	def read_json(self: Any) -> dict[str, Any]:
		raw = self.headers.get("Content-Length", "0")
		try:
			length = int(raw)
		except (TypeError, ValueError) as exc:
			raise controller_module.WebConsoleError("INVALID_LENGTH", "Content-Length 无效", status=400) from exc
		if length < 0:
			raise controller_module.WebConsoleError("INVALID_LENGTH", "Content-Length 不能为负数", status=400)
		return original_read(self)

	setattr(handler_cls, "_read_json", read_json)
