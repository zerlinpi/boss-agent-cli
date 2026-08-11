"""Strict, transactional preflight for recruiter Web AI settings."""

from __future__ import annotations

import math
from typing import Any, Callable

from boss_agent_cli.ai.config import PROVIDER_BASE_URLS, _validate_config
from boss_agent_cli.web import controller as controller_module

_INSTALLED = False


def _text(value: Any, *, label: str, allow_empty: bool = False) -> str:
	if not isinstance(value, str):
		raise controller_module.WebConsoleError("INVALID_AI_CONFIG", f"{label} 必须是字符串")
	text = value.strip()
	if not allow_empty and not text:
		raise controller_module.WebConsoleError("INVALID_AI_CONFIG", f"{label} 不能为空")
	return text


def _temperature(value: Any) -> float:
	if isinstance(value, bool):
		raise controller_module.WebConsoleError("INVALID_AI_CONFIG", "temperature 必须是 0-2 的有限数字")
	try:
		number = float(value)
	except (TypeError, ValueError) as exc:
		raise controller_module.WebConsoleError("INVALID_AI_CONFIG", "temperature 必须是 0-2 的有限数字") from exc
	if not math.isfinite(number) or not 0 <= number <= 2:
		raise controller_module.WebConsoleError("INVALID_AI_CONFIG", "temperature 必须是 0-2 的有限数字")
	return number


def _max_tokens(value: Any) -> int:
	if isinstance(value, bool):
		raise controller_module.WebConsoleError("INVALID_AI_CONFIG", "max_tokens 必须是 1-1000000 的整数")
	try:
		number = int(value)
	except (TypeError, ValueError) as exc:
		raise controller_module.WebConsoleError("INVALID_AI_CONFIG", "max_tokens 必须是 1-1000000 的整数") from exc
	if str(value).strip() not in {str(number), f"+{number}"} and not isinstance(value, int):
		raise controller_module.WebConsoleError("INVALID_AI_CONFIG", "max_tokens 必须是整数")
	if not 1 <= number <= 1_000_000:
		raise controller_module.WebConsoleError("INVALID_AI_CONFIG", "max_tokens 必须是 1-1000000 的整数")
	return number


def install_ai_config_safety() -> None:
	"""Validate the complete merged AI config before the controller writes any file."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True
	controller_cls = controller_module.RecruiterWebController
	original_configure: Callable[..., dict[str, Any]] = controller_cls.configure_ai

	def configure_ai(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
		clean = dict(payload)
		provider = _text(clean.get("provider"), label="provider")
		if provider not in PROVIDER_BASE_URLS:
			raise controller_module.WebConsoleError("INVALID_AI_CONFIG", f"不支持的 AI provider: {provider}")
		model = _text(clean.get("model"), label="model")
		base_url = _text(clean.get("base_url", ""), label="base_url", allow_empty=True)
		api_key = _text(clean.get("api_key", ""), label="api_key", allow_empty=True)
		temperature = _temperature(clean.get("temperature", 0.2))
		max_tokens = _max_tokens(clean.get("max_tokens", 4096))
		if provider == "custom" and not base_url:
			raise controller_module.WebConsoleError("INVALID_AI_CONFIG", "custom provider 必须填写 Base URL")

		merged = self.ai_store.load_config()
		merged.update({
			"ai_provider": provider,
			"ai_model": model,
			"ai_base_url": base_url or None,
			"ai_temperature": temperature,
			"ai_max_tokens": max_tokens,
		})
		try:
			_validate_config(merged)
		except ValueError as exc:
			raise controller_module.WebConsoleError("INVALID_AI_CONFIG", str(exc)) from exc
		if api_key and len(api_key) > 8192:
			raise controller_module.WebConsoleError("INVALID_AI_CONFIG", "API Key 过长，最多 8192 字符")

		clean.update({
			"provider": provider,
			"model": model,
			"base_url": base_url,
			"api_key": api_key,
			"temperature": temperature,
			"max_tokens": max_tokens,
		})
		try:
			return original_configure(self, clean)
		except ValueError as exc:
			raise controller_module.WebConsoleError("INVALID_AI_CONFIG", str(exc)) from exc

	setattr(controller_cls, "configure_ai", configure_ai)
