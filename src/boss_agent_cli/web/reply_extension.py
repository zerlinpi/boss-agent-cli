"""Install reply-safety UI assets into the no-build Web bundle."""

from __future__ import annotations

from importlib.resources import files
from typing import Any, Callable

_INSTALLED = False


def install_reply_assets(server_module: Any) -> None:
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True
	application_cls = server_module.RecruiterWebApplication
	original_asset: Callable[..., tuple[bytes, str]] = application_cls.asset

	def asset(self: Any, name: str) -> tuple[bytes, str]:
		content, content_type = original_asset(self, name)
		if name == "app.js":
			content += b"\n" + files("boss_agent_cli.web.assets").joinpath("reply_safety.js").read_bytes()
		elif name == "styles.css":
			content += b"\n" + files("boss_agent_cli.web.assets").joinpath("reply_safety.css").read_bytes()
		return content, content_type

	setattr(application_cls, "asset", asset)
