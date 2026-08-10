"""Operational privacy boundaries for recruiter model input and locally stored conversations."""

from __future__ import annotations

import re
from typing import Any, Callable

_GENERIC_PROTECTED_CRITERIA: tuple[tuple[re.Pattern[str], str], ...] = (
	(
		re.compile(
			r"(?:婚姻(?:状况)?|婚育|marital\s*status|marriage|fertility)"
			r"\s*(?:稳定(?:性)?|偏好|要求|限制|门槛|优先|加分|减分|preferred?|requirement)",
			re.I,
		),
		"[婚姻婚育条件已隔离]",
	),
	(
		re.compile(
			r"(?:年龄|age)\s*(?:偏好|要求|限制|门槛|范围|优先|加分|减分|preferred?|requirement|limit)",
			re.I,
		),
		"[年龄条件已隔离]",
	),
	(
		re.compile(
			r"(?:性别|gender|sex)\s*(?:偏好|要求|限制|门槛|优先|加分|减分|preferred?|requirement)",
			re.I,
		),
		"[性别条件已隔离]",
	),
	(
		re.compile(
			r"(?:民族|种族|宗教|政治面貌|政治身份|健康状况|残障状况|"
			r"ethnicity|race|religion|political\s*(?:status|affiliation)|health\s*status|disability)"
			r"\s*(?:偏好|要求|限制|门槛|优先|加分|减分|preferred?|requirement)",
			re.I,
		),
		"[受保护属性条件已隔离]",
	),
)

_ID_NUMBER_RE = re.compile(r"(?<!\d)(?:\d{17}[\dXx]|\d{15})(?!\d)")
_ADDRESS_FIELD_RE = re.compile(
	r"(?:家庭住址|详细地址|居住地址|现住址|住址|地址|home\s*address|residential\s*address)"
	r"\s*[:：]?\s*[^\n\r;；]{4,120}",
	re.I,
)


def sanitize_generic_protected_text(text: str) -> str:
	"""Remove generic protected-attribute criteria that do not contain a concrete trait value."""
	result = text
	for pattern, replacement in _GENERIC_PROTECTED_CRITERIA:
		result = pattern.sub(replacement, result)
	return result


def sanitize_local_conversation(text: str) -> str:
	"""Keep recruiter-useful contacts while removing non-operational identity/address data."""
	result = _ID_NUMBER_RE.sub("[身份证号已移除]", text)
	return _ADDRESS_FIELD_RE.sub("[详细地址已移除]", result)


def _sanitize_nested_text(value: Any) -> Any:
	if isinstance(value, dict):
		return {key: _sanitize_nested_text(item) for key, item in value.items()}
	if isinstance(value, list):
		return [_sanitize_nested_text(item) for item in value]
	if isinstance(value, str):
		return sanitize_generic_protected_text(value)
	return value


def install_operational_privacy(model_module: Any, store_cls: type[Any]) -> None:
	"""Install model-input and local-conversation privacy hardening once."""
	if getattr(model_module, "_operational_privacy_installed", False):
		return

	base_redact_contact: Callable[[str], str] = model_module.redact_contact_text
	base_redact_resume: Callable[[dict[str, Any]], dict[str, Any]] = model_module.redact_resume_for_model
	base_save_reply = store_cls.save_reply

	def redact_contact_text(text: str) -> str:
		return sanitize_generic_protected_text(base_redact_contact(text))

	def redact_resume_for_model(resume: dict[str, Any]) -> dict[str, Any]:
		return _sanitize_nested_text(base_redact_resume(resume))

	def save_reply(self: Any, **kwargs: Any) -> dict[str, Any]:
		conversation = kwargs.get("conversation")
		if isinstance(conversation, str):
			kwargs["conversation"] = sanitize_local_conversation(conversation)
		return base_save_reply(self, **kwargs)

	model_module.redact_contact_text = redact_contact_text
	model_module.redact_resume_for_model = redact_resume_for_model
	setattr(store_cls, "save_reply", save_reply)
	setattr(model_module, "_operational_privacy_installed", True)
