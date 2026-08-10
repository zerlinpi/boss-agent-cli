"""Container-specific recruiter login guardrails."""

from __future__ import annotations

import os
from typing import Any, Callable

from boss_agent_cli.auth.browser import probe_cdp
from boss_agent_cli.auth.manager import AuthManager, TokenRefreshFailed
from boss_agent_cli.web import controller as controller_module

_INSTALLED = False
_CONTAINER_VALUES = {"1", "true", "yes"}


def _is_container() -> bool:
	return os.getenv("BOSS_RECRUITER_CONTAINER", "").strip().lower() in _CONTAINER_VALUES


def _configured_cdp(controller: Any) -> str:
	value = controller.cdp_url or controller._config().get("cdp_url")
	return value.strip() if isinstance(value, str) else ""


def _refresh_cdp_url(cdp_url: str | None) -> str:
	value = cdp_url or os.getenv("BOSS_CDP_URL") or ""
	return value.strip()


def install_container_auth_guard() -> None:
	"""Require an explicit host CDP channel for interactive login and refresh inside Docker."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	original_login: Callable[..., dict[str, Any]] = controller_cls.login
	original_auth_status: Callable[..., dict[str, Any]] = controller_cls.auth_status
	original_force_refresh: Callable[..., None] = AuthManager.force_refresh

	def auth_status(self: Any) -> dict[str, Any]:
		status = original_auth_status(self)
		if _is_container() and not _configured_cdp(self):
			status = dict(status)
			status["container_cdp_required"] = True
			if status.get("logged_in"):
				base = str(status.get("summary") or "").strip()
				warning = "Docker 模式若 BOSS 登录态需要刷新，必须配置 BOSS_CDP_URL。"
				status["summary"] = f"{base}；{warning}" if base else warning
			else:
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

	def force_refresh(self: AuthManager, cdp_url: str | None = None) -> None:
		if not _is_container():
			return original_force_refresh(self, cdp_url=cdp_url)

		resolved = _refresh_cdp_url(cdp_url)
		if not resolved:
			raise TokenRefreshFailed(
				"Docker 模式无法在容器内刷新 BOSS 登录态；请配置 BOSS_CDP_URL，"
				"或使用 Windows 非 Docker 启动重新登录。"
			)
		if not probe_cdp(resolved):
			raise TokenRefreshFailed("Docker 模式配置的 BOSS_CDP_URL 当前不可达，请检查宿主机 Chrome 调试端口。")
		return original_force_refresh(self, cdp_url=resolved)

	setattr(controller_cls, "auth_status", auth_status)
	setattr(controller_cls, "login", login)
	setattr(AuthManager, "force_refresh", force_refresh)
