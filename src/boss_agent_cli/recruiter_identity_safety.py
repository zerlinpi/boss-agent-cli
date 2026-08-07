"""Final identity-alias scrub for recruiter model payloads."""

from __future__ import annotations

from typing import Any, cast

import boss_agent_cli.recruiter_ai_models as model_module

_INSTALLED = False
_ROOT_NAME_KEYS = ("name", "candidateName", "candidate_name", "geekName", "geek_name", "姓名", "候选人姓名")


def _candidate_identity(resume: dict[str, Any]) -> str:
	basic = resume.get("basic")
	if isinstance(basic, dict):
		for key in _ROOT_NAME_KEYS:
			value = basic.get(key)
			if isinstance(value, str) and len(value.strip()) >= 2:
				return value.strip()
	for key in _ROOT_NAME_KEYS:
		value = resume.get(key)
		if isinstance(value, str) and len(value.strip()) >= 2:
			return value.strip()
	return ""


def _replace_identity(value: Any, identity: str) -> Any:
	if isinstance(value, dict):
		for key in list(value):
			value[key] = _replace_identity(value[key], identity)
		return value
	if isinstance(value, list):
		for index, item in enumerate(value):
			value[index] = _replace_identity(item, identity)
		return value
	if isinstance(value, str) and identity:
		return value.replace(identity, "[姓名已脱敏]")
	return value


def install_identity_alias_sanitizer() -> None:
	"""Wrap the active resume sanitizer so name aliases cannot remain in free text."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True
	base = model_module.redact_resume_for_model

	def redact_resume_for_model(resume: dict[str, Any]) -> dict[str, Any]:
		identity = _candidate_identity(resume)
		redacted = base(resume)
		return cast("dict[str, Any]", _replace_identity(redacted, identity))

	model_module.redact_resume_for_model = redact_resume_for_model
