"""Install small recruiter UI reliability helpers."""

from __future__ import annotations

from importlib.resources import files
from typing import Any, Callable

_INSTALLED = False


def install_ui_reliability_assets(server_module: Any) -> None:
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True
	application_cls = server_module.RecruiterWebApplication
	original_asset: Callable[..., tuple[bytes, str]] = application_cls.asset

	def asset(self: Any, name: str) -> tuple[bytes, str]:
		content, content_type = original_asset(self, name)
		assets = files("boss_agent_cli.web.assets")
		if name == "app.js":
			content += b"\n" + assets.joinpath("ui_reliability.js").read_bytes()
			content += b"\n" + assets.joinpath("ui_cache_consistency.js").read_bytes()
			content += b"\n" + assets.joinpath("ui_request_consistency.js").read_bytes()
			content += b"\n" + assets.joinpath("guided_setup.js").read_bytes()
			content += b"\n" + assets.joinpath("guided_navigation.js").read_bytes()
			content += b"\n" + assets.joinpath("guided_feedback.js").read_bytes()
			content += b"\n" + assets.joinpath("guided_autopilot_feedback.js").read_bytes()
			content += b"\n" + assets.joinpath("product_workbench.js").read_bytes()
		elif name == "styles.css":
			content += b"\n" + assets.joinpath("guided_feedback.css").read_bytes()
			content += b"\n" + assets.joinpath("guided_visual.css").read_bytes()
			content += b"\n" + assets.joinpath("product_workbench.css").read_bytes()
		return content, content_type

	setattr(application_cls, "asset", asset)
