"""Container-specific recruiter login guardrails."""

from __future__ import annotations

import os
from typing import Any, Callable

from boss_agent_cli.web import controller as controller_module

_INSTALLED = False
_CONTAINER_VALUES = {"1", "true", "yes"}


def _is_container() -> bool:
	return os.getenv("BOSS_RECRUITER_CONTAINER", "").strip().lower() in _CONTAINER_VALUES


def _configured_cdp(controller: Any) -> str:
	value = controller.cdp_url or controller._config().get("cdp_url")
	return value.strip() if isinstance(value, str) else ""


def install_container_auth_guard() -> None:
	"""Require an explicit host CDP channel for interactive login inside Docker."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	original_login: Callable[..., dict[str, Any]] = controller_cls.login
	original_auth_status: Callable[..., dict[str, Any]] = controller_cls.auth_status

	def auth_status(self: Any) -> dict[str, Any]:
		status = original_auth_status(self)
		if _is_container() and not status.get("logged_in") and not _configured_cdp(self):
			status = dict(status)
			status["summary"] = (
				"Docker 模式的 BOSS 交互登录需要宿主机 Chrome CDP。"
				"请设置 BOSS_CDP_URL；本地简历上传与 AI 筛选不受影响。"
			)
		return status

	def login(self: Any, **kwargs: Any) -> dict[str, Any]:
		if not _is_container():
			return original_login(self, **kwargs)

		cdp_url = _configured_cdp(self)
		if not cdp_url:
			raise controller_module.WebConsoleError(
				"CONTAINER_CDP_REQUIRED",
				"Docker 模式无法直接打开宿主机登录浏览器。请设置 BOSS_CDP_URL 指向可访问的 Chrome CDP，"
				"或改用 Windows 非 Docker 一键启动完成 BOSS 登录。",
				status=409,
			)

		clean = dict(kwargs)
		clean["force_cdp"] = True
		return original_login(self, **clean)

	setattr(controller_cls, "auth_status", auth_status)
	setattr(controller_cls, "login", login)
