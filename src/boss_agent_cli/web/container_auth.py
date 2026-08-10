"""Container-specific recruiter login guardrails."""

from __future__ import annotations

import os
from typing import Any, Callable

from boss_agent_cli.web import controller as controller_module

_INSTALLED = False


def install_container_auth_guard() -> None:
	"""Require an explicit host CDP channel for interactive login inside Docker."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	original_login: Callable[..., dict[str, Any]] = controller_cls.login

	def login(self: Any, **kwargs: Any) -> dict[str, Any]:
		if os.getenv("BOSS_RECRUITER_CONTAINER", "").strip() not in {"1", "true", "yes"}:
			return original_login(self, **kwargs)

		cdp_url = self.cdp_url or self._config().get("cdp_url")
		if not isinstance(cdp_url, str) or not cdp_url.strip():
			raise controller_module.WebConsoleError(
				"CONTAINER_CDP_REQUIRED",
				"Docker 模式无法直接打开宿主机登录浏览器。请设置 BOSS_CDP_URL 指向可访问的 Chrome CDP，"
				"或改用 Windows 非 Docker 一键启动完成 BOSS 登录。",
				status=409,
			)

		clean = dict(kwargs)
		clean["force_cdp"] = True
		return original_login(self, **clean)

	setattr(controller_cls, "login", login)
