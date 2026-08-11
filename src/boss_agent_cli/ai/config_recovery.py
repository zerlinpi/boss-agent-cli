"""Read-time recovery for legacy or partially corrupt AI configuration."""

from __future__ import annotations

import math
from typing import Any, Callable

from boss_agent_cli.ai.config import AIConfigStore, PROVIDER_BASE_URLS, _validate_base_url

_INSTALLED = False
_DEFAULT_TEMPERATURE = 0.7
_DEFAULT_MAX_TOKENS = 4096
_MAX_MODEL_CHARS = 256
_MAX_API_KEY_CHARS = 8192


def _safe_provider(value: Any) -> str | None:
	return value if isinstance(value, str) and value in PROVIDER_BASE_URLS else None


def _safe_model(value: Any) -> str | None:
	if not isinstance(value, str):
		return None
	model = value.strip()
	return model if model and len(model) <= _MAX_MODEL_CHARS else None


def _safe_base_url(value: Any) -> str | None:
	try:
		return _validate_base_url(value)
	except ValueError:
		return None


def _safe_temperature(value: Any) -> float:
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		return _DEFAULT_TEMPERATURE
	number = float(value)
	return number if math.isfinite(number) and 0 <= number <= 2 else _DEFAULT_TEMPERATURE


def _safe_max_tokens(value: Any) -> int:
	if isinstance(value, bool) or not isinstance(value, int):
		return _DEFAULT_MAX_TOKENS
	return value if 1 <= value <= 1_000_000 else _DEFAULT_MAX_TOKENS


def install_ai_config_recovery() -> None:
	"""Sanitize each persisted field independently instead of failing the whole config."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True
	original_load: Callable[[AIConfigStore], dict[str, Any]] = AIConfigStore.load_config
	original_get_key: Callable[[AIConfigStore], str | None] = AIConfigStore.get_api_key

	def load_config(self: AIConfigStore) -> dict[str, Any]:
		config = original_load(self)
		return {
			"ai_provider": _safe_provider(config.get("ai_provider")),
			"ai_model": _safe_model(config.get("ai_model")),
			"ai_base_url": _safe_base_url(config.get("ai_base_url")),
			"ai_temperature": _safe_temperature(config.get("ai_temperature")),
			"ai_max_tokens": _safe_max_tokens(config.get("ai_max_tokens")),
		}

	def get_api_key(self: AIConfigStore) -> str | None:
		try:
			value = original_get_key(self)
		except ValueError:
			return None
		if value is None:
			return None
		if not isinstance(value, str) or not value.strip() or len(value) > _MAX_API_KEY_CHARS:
			return None
		return value

	setattr(AIConfigStore, "load_config", load_config)
	setattr(AIConfigStore, "get_api_key", get_api_key)
