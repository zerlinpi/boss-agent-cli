"""Deep fail-closed validation for persisted automation state."""

from __future__ import annotations

import math
from typing import Any, Callable, cast

from boss_agent_cli.automation.models import PlatformAction
from boss_agent_cli.automation.storage import AutomationStorageError

_INSTALLED = False


def _finite_unit(value: Any, *, label: str) -> float:
	if isinstance(value, bool):
		raise AutomationStorageError(f"state.json 损坏：{label} 必须是 0-1 的有限数字")
	try:
		number = float(value)
	except (TypeError, ValueError) as exc:
		raise AutomationStorageError(f"state.json 损坏：{label} 必须是 0-1 的有限数字") from exc
	if not math.isfinite(number) or not 0 <= number <= 1:
		raise AutomationStorageError(f"state.json 损坏：{label} 必须是 0-1 的有限数字")
	return number


def _nonnegative_int(value: Any, *, label: str) -> int:
	if isinstance(value, bool):
		raise AutomationStorageError(f"state.json 损坏：{label} 必须是非负整数")
	try:
		number = float(value)
	except (TypeError, ValueError) as exc:
		raise AutomationStorageError(f"state.json 损坏：{label} 必须是非负整数") from exc
	if not math.isfinite(number) or not number.is_integer() or number < 0:
		raise AutomationStorageError(f"state.json 损坏：{label} 必须是非负整数")
	return int(number)


def _validate_inflight(value: Any, *, candidate_key: str) -> None:
	if value is None:
		return
	if not isinstance(value, dict):
		raise AutomationStorageError(
			f"state.json 损坏：conversations[{candidate_key!r}].inflight_action 必须是对象"
		)
	action = value.get("action")
	try:
		PlatformAction(str(action or ""))
	except ValueError as exc:
		raise AutomationStorageError(
			f"state.json 损坏：conversations[{candidate_key!r}].inflight_action.action 无效"
		) from exc
	if "confidence" in value:
		_finite_unit(
			value.get("confidence"),
			label=f"conversations[{candidate_key!r}].inflight_action.confidence",
		)
	for field in ("started_at", "message", "reason", "verification_review_id", "status"):
		if field in value and not isinstance(value[field], str):
			raise AutomationStorageError(
				f"state.json 损坏：conversations[{candidate_key!r}].inflight_action.{field} 必须是字符串"
			)


def validate_nested_state(payload: dict[str, Any]) -> dict[str, Any]:
	"""Validate nested shapes relied upon by SafetyGuard and side-effect checkpoints."""
	conversations = payload.get("conversations", {})
	autonomy = payload.get("autonomy", {})
	safety = payload.get("safety", {})
	if not isinstance(conversations, dict) or not isinstance(autonomy, dict) or not isinstance(safety, dict):
		raise AutomationStorageError("state.json 损坏：已知顶层状态必须是对象")

	for raw_key, prior in conversations.items():
		candidate_key = str(raw_key)
		if not isinstance(prior, dict):
			raise AutomationStorageError(
				f"state.json 损坏：conversations[{candidate_key!r}] 必须是对象"
			)
		_validate_inflight(prior.get("inflight_action"), candidate_key=candidate_key)

	circuit_breaker = autonomy.get("circuit_breaker")
	if circuit_breaker is not None:
		if not isinstance(circuit_breaker, dict):
			raise AutomationStorageError("state.json 损坏：autonomy.circuit_breaker 必须是对象")
		if "open" in circuit_breaker and not isinstance(circuit_breaker["open"], bool):
			raise AutomationStorageError("state.json 损坏：autonomy.circuit_breaker.open 必须是布尔值")
		for field in ("reason", "opened_at"):
			if field in circuit_breaker and not isinstance(circuit_breaker[field], str):
				raise AutomationStorageError(
					f"state.json 损坏：autonomy.circuit_breaker.{field} 必须是字符串"
				)

	if "consecutive_errors" in safety:
		safety["consecutive_errors"] = _nonnegative_int(
			safety.get("consecutive_errors"),
			label="safety.consecutive_errors",
		)
	for field in ("last_action_at", "last_error"):
		if field in safety and not isinstance(safety[field], str):
			raise AutomationStorageError(f"state.json 损坏：safety.{field} 必须是字符串")
	return payload


def install_nested_state_validation(store_cls: type[Any]) -> None:
	"""Extend AutomationStore's root validation without replacing persistence logic."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True
	original: Callable[[Any], dict[str, Any]] = store_cls._validate_state

	def validate(payload: Any) -> dict[str, Any]:
		state = original(payload)
		return validate_nested_state(cast("dict[str, Any]", state))

	setattr(store_cls, "_validate_state", staticmethod(validate))
