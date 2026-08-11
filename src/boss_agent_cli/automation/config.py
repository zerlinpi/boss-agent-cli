"""Automation configuration parsing with conservative defaults."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, unique
from typing import Any, Final

from boss_agent_cli.automation.models import AutomationMode, PlatformAction

DEFAULT_ALLOWED_ACTIONS: Final = (
	PlatformAction.SCAN_CONVERSATIONS,
	PlatformAction.READ_CANDIDATE_PROFILE,
	PlatformAction.SEND_QUESTIONNAIRE,
	PlatformAction.SEND_FOLLOW_UP,
	PlatformAction.EXCHANGE_CONTACT,
	PlatformAction.CREATE_INTERVIEW_LEAD,
)


@unique
class ReplyStrategy(str, Enum):
	TEMPLATE = "template"
	LOCAL_AI = "local_ai"
	HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class AutomationConfig:
	mode: AutomationMode = AutomationMode.AUTONOMOUS
	platforms: tuple[str, ...] = ("zhilian", "zhipin")
	allowed_actions: tuple[PlatformAction, ...] = DEFAULT_ALLOWED_ACTIONS
	human_review_threshold: float = 0.65
	auto_execute_threshold: float = 0.82
	max_actions_per_run: int = 50
	max_consecutive_errors: int = 3
	tabs: tuple[str, ...] = ("新招呼", "未读")
	max_per_tab: int = 20
	questionnaire_message: str = "您好，想确认下近期是否看机会？"
	follow_up_message: str = (
		"谢谢回复，我这边同步岗位信息，方便的话可以继续沟通面试时间。"
	)
	reply_strategy: ReplyStrategy = ReplyStrategy.HYBRID
	stop_on_page_text: tuple[str, ...] = (
		"验证码",
		"安全验证",
		"操作频繁",
		"账号异常",
		"访问受限",
	)


_DEFAULT = AutomationConfig()


def _unit(value: Any, *, label: str) -> float:
	if isinstance(value, bool):
		raise ValueError(f"{label} 必须是 0-1 的有限数字")
	try:
		number = float(value)
	except (TypeError, ValueError) as exc:
		raise ValueError(f"{label} 必须是 0-1 的有限数字") from exc
	if not math.isfinite(number) or not 0 <= number <= 1:
		raise ValueError(f"{label} 必须是 0-1 的有限数字")
	return number


def _bounded_integer(value: Any, *, label: str, minimum: int, maximum: int) -> int:
	if isinstance(value, bool):
		raise ValueError(f"{label} 必须是 {minimum}-{maximum} 的整数")
	try:
		number = float(value)
	except (TypeError, ValueError) as exc:
		raise ValueError(f"{label} 必须是 {minimum}-{maximum} 的整数") from exc
	if not math.isfinite(number) or not number.is_integer() or not minimum <= number <= maximum:
		raise ValueError(f"{label} 必须是 {minimum}-{maximum} 的整数")
	return int(number)


def _string_tuple(value: Any, *, label: str, default: tuple[str, ...]) -> tuple[str, ...]:
	if value is None:
		return default
	if not isinstance(value, (list, tuple)):
		raise ValueError(f"{label} 必须是数组")
	return tuple(str(item).strip() for item in value if str(item).strip())


def _allowed_actions(data: dict[str, Any]) -> tuple[PlatformAction, ...]:
	if "allowed_actions" not in data:
		return DEFAULT_ALLOWED_ACTIONS
	raw = data.get("allowed_actions")
	if not isinstance(raw, (list, tuple)):
		raise ValueError("allowed_actions 必须是数组")
	allowed_action_values = {action.value for action in PlatformAction}
	values = [str(item).strip() for item in raw if str(item).strip()]
	unknown = sorted({value for value in values if value not in allowed_action_values})
	if unknown:
		raise ValueError(f"allowed_actions 包含未知动作: {', '.join(unknown)}")
	return tuple(PlatformAction(value) for value in values)


def automation_config_from_dict(raw: dict[str, Any] | None) -> AutomationConfig:
	"""Parse automation config and reject values that could weaken safety gates."""
	if raw is not None and not isinstance(raw, dict):
		raise ValueError("automation 配置必须是对象")
	data = raw or {}
	human_review_threshold = _unit(
		data.get("human_review_threshold", _DEFAULT.human_review_threshold),
		label="human_review_threshold",
	)
	auto_execute_threshold = _unit(
		data.get("auto_execute_threshold", _DEFAULT.auto_execute_threshold),
		label="auto_execute_threshold",
	)
	if human_review_threshold > auto_execute_threshold:
		raise ValueError("自动化阈值必须满足 human_review_threshold <= auto_execute_threshold")

	return AutomationConfig(
		mode=AutomationMode(data.get("mode", _DEFAULT.mode.value)),
		platforms=_string_tuple(data.get("platforms"), label="platforms", default=_DEFAULT.platforms),
		allowed_actions=_allowed_actions(data),
		human_review_threshold=human_review_threshold,
		auto_execute_threshold=auto_execute_threshold,
		max_actions_per_run=_bounded_integer(
			data.get("max_actions_per_run", _DEFAULT.max_actions_per_run),
			label="max_actions_per_run",
			minimum=1,
			maximum=10000,
		),
		max_consecutive_errors=_bounded_integer(
			data.get("max_consecutive_errors", _DEFAULT.max_consecutive_errors),
			label="max_consecutive_errors",
			minimum=1,
			maximum=100,
		),
		tabs=_string_tuple(data.get("tabs"), label="tabs", default=_DEFAULT.tabs),
		max_per_tab=_bounded_integer(
			data.get("max_per_tab", _DEFAULT.max_per_tab),
			label="max_per_tab",
			minimum=1,
			maximum=10000,
		),
		questionnaire_message=str(data.get("questionnaire_message", _DEFAULT.questionnaire_message)),
		follow_up_message=str(data.get("follow_up_message", _DEFAULT.follow_up_message)),
		reply_strategy=ReplyStrategy(data.get("reply_strategy", _DEFAULT.reply_strategy.value)),
		stop_on_page_text=_string_tuple(
			data.get("stop_on_page_text"),
			label="stop_on_page_text",
			default=_DEFAULT.stop_on_page_text,
		),
	)
