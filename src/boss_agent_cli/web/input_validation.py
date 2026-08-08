"""Deterministic input validation for recruiter Web settings and text-heavy operations."""

from __future__ import annotations

import math
from typing import Any, Callable
from urllib.parse import urlparse

from boss_agent_cli.web import controller as controller_module

_INSTALLED = False
MAX_JD_CHARS = 200_000
MAX_CONVERSATION_CHARS = 200_000
MAX_MODEL_NAME_CHARS = 256
MAX_API_KEY_CHARS = 16_384
_ALLOWED_REPLY_INTENTS = {
	"auto",
	"acknowledge",
	"ask_followup",
	"invite_interview",
	"clarify",
	"decline_draft",
}


def _temperature(value: Any) -> float:
	if value in (None, ""):
		return 0.2
	if isinstance(value, bool):
		raise controller_module.WebConsoleError("INVALID_TEMPERATURE", "temperature 必须是 0-2 的有限数字")
	try:
		number = float(value)
	except (TypeError, ValueError) as exc:
		raise controller_module.WebConsoleError("INVALID_TEMPERATURE", "temperature 必须是 0-2 的有限数字") from exc
	if not math.isfinite(number) or not 0 <= number <= 2:
		raise controller_module.WebConsoleError("INVALID_TEMPERATURE", "temperature 必须是 0-2 的有限数字")
	return number


def _max_tokens(value: Any) -> int:
	if value in (None, ""):
		return 4096
	if isinstance(value, bool):
		raise controller_module.WebConsoleError("INVALID_MAX_TOKENS", "max_tokens 必须是 256-32768 的整数")
	try:
		number = int(value)
		except (TypeError, ValueError) as exc:
		raise controller_module.WebConsoleError("INVALID_MAX_TOKENS", "max_tokens 必须是 256-32768 的整数") from exc
	if str(value).strip() not in {str(number), f"+{number}"} and not isinstance(value, int):
		raise controller_module.WebConsoleError("INVALID_MAX_TOKENS", "max_tokens 必须是 256-32768 的整数")
	if not 256 <= number <= 32768:
		raise controller_module.WebConsoleError("INVALID_MAX_TOKENS", "max_tokens 必须是 256-32768 的整数")
	return number


def _validated_base_url(value: str | None, *, required: bool) -> str | None:
	url = str(value or "").strip().rstrip("/")
	if not url:
		if required:
			raise controller_module.WebConsoleError("INVALID_BASE_URL", "custom provider 必须填写 Base URL")
		return None
	parsed = urlparse(url)
	if parsed.scheme not in {"http", "https"} or not parsed.netloc:
		raise controller_module.WebConsoleError("INVALID_BASE_URL", "Base URL 必须是完整的 HTTP(S) 地址")
	if parsed.username or parsed.password:
		raise controller_module.WebConsoleError("INVALID_BASE_URL", "Base URL 不能包含用户名或密码")
	return url


def _bounded_text(value: Any, *, label: str, limit: int, code: str) -> str:
	text = str(value or "")
	if len(text) > limit:
		raise controller_module.WebConsoleError(
			code,
			f"{label} 不能超过 {limit} 个字符",
			status=413,
		)
	return text


def install_controller_input_validation() -> None:
	"""Install structured validation before settings are persisted or text is sent to a model."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	controller_cls = controller_module.RecruiterWebController
	original_configure_ai: Callable[..., dict[str, Any]] = controller_cls.configure_ai
	original_analyze_job: Callable[..., dict[str, Any]] = controller_cls.analyze_job
	original_save_job: Callable[..., dict[str, Any]] = controller_cls.save_job
	original_generate_reply: Callable[..., dict[str, Any]] = controller_cls.generate_reply

	def configure_ai(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
		safe = dict(payload)
		provider = str(safe.get("provider") or "").strip()
		model = str(safe.get("model") or "").strip()
		api_key = str(safe.get("api_key") or "")
		if len(model) > MAX_MODEL_NAME_CHARS:
			raise controller_module.WebConsoleError("INVALID_MODEL", "模型名称过长")
		if len(api_key) > MAX_API_KEY_CHARS:
			raise controller_module.WebConsoleError("INVALID_API_KEY", "API Key 长度异常")
		safe["temperature"] = _temperature(safe.get("temperature"))
		safe["max_tokens"] = _max_tokens(safe.get("max_tokens"))
		safe["base_url"] = _validated_base_url(safe.get("base_url"), required=provider == "custom")
		return original_configure_ai(self, safe)

	def analyze_job(self: Any, payload: dict[str, Any], *, progress: Any = None) -> dict[str, Any]:
		safe = dict(payload)
		safe["jd_text"] = _bounded_text(
			safe.get("jd_text"), label="岗位 JD", limit=MAX_JD_CHARS, code="JD_TOO_LARGE",
		)
		return original_analyze_job(self, safe, progress=progress)

	def save_job(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
		if payload.get("_delete"):
			return original_save_job(self, payload)
		safe = dict(payload)
		safe["jd_text"] = _bounded_text(
			safe.get("jd_text"), label="岗位 JD", limit=MAX_JD_CHARS, code="JD_TOO_LARGE",
		)
		return original_save_job(self, safe)

	def generate_reply(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
		safe = dict(payload)
		intent = str(safe.get("intent") or "auto").strip()
		if intent not in _ALLOWED_REPLY_INTENTS:
			raise controller_module.WebConsoleError("INVALID_REPLY_INTENT", f"不支持的回复意图: {intent}")
		safe["intent"] = intent
		safe["conversation"] = _bounded_text(
			safe.get("conversation"),
			label="聊天上下文",
			limit=MAX_CONVERSATION_CHARS,
			code="CONVERSATION_TOO_LARGE",
		)
		return original_generate_reply(self, safe)

	setattr(controller_cls, "configure_ai", configure_ai)
	setattr(controller_cls, "analyze_job", analyze_job)
	setattr(controller_cls, "save_job", save_job)
	setattr(controller_cls, "generate_reply", generate_reply)
