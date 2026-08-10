"""Cross-process-safe persistence for recruiter Web global settings."""

from __future__ import annotations

from typing import Any

from boss_agent_cli.config import ConfigLockBusy, update_user_config
from boss_agent_cli.web import controller as controller_module

_INSTALLED = False


def install_web_config_persistence() -> None:
	"""Keep Web mode changes from overwriting concurrent CLI config updates."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController

	def set_operating_mode(self: Any, mode: str) -> dict[str, Any]:
		if mode not in controller_module.AVAILABLE_OPERATING_MODES:
			raise controller_module.WebConsoleError("INVALID_MODE", f"不支持的运行模式: {mode}")
		try:
			update_user_config(
				self.config_path,
				updates={"operating_mode": mode, "low_risk_mode": mode != "research"},
			)
		except ConfigLockBusy as exc:
			raise controller_module.WebConsoleError("CONFIG_BUSY", str(exc), status=409) from exc
		except OSError as exc:
			raise controller_module.WebConsoleError("CONFIG_WRITE_FAILED", "系统配置保存失败", status=500) from exc
		self.audit.append(
			"settings.mode.updated",
			entity_type="settings",
			entity_id="operating_mode",
			summary=f"运行模式切换为 {mode}",
			metadata={"mode": mode},
		)
		return {"operating_mode": mode}

	setattr(controller_cls, "set_operating_mode", set_operating_mode)
