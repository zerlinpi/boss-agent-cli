"""High-risk identity-data removal shared by recruiter local and model paths."""

from __future__ import annotations

import re
from typing import Any, Callable, cast

from boss_agent_cli.recruiter_ai_store import _safe_storage_key

_INSTALLED = False
_FIELD_NORMALIZER = re.compile(r"[^a-z0-9\u4e00-\u9fff]+")
_CN_ID_RE = re.compile(
	r"(?<!\d)(?:"
	r"\d{6}[\s-]?(?:18|19|20)\d{2}[\s-]?(?:0[1-9]|1[0-2])[\s-]?(?:0[1-9]|[12]\d|3[01])"
	r"[\s-]?\d{3}[\dXx]"
	r"|\d{6}[\s-]?\d{6}[\s-]?\d{3}"
	r")(?!\d)"
)
_PASSPORT_RE = re.compile(
	r"(?:护照号|护照号码|passport\s*(?:no\.?|number))\s*[:：#]?\s*[A-Z0-9]{5,20}",
	re.IGNORECASE,
)
_RESIDENTIAL_ADDRESS_RE = re.compile(
	r"(?:家庭住址|家庭地址|现住址|现居住址|居住地址|住宅地址|详细住址|住址)"
	r"(?:\s*[:：]\s*|\s+)[^\n,，;；]{4,160}",
)
_HIGH_RISK_PATTERNS = (_CN_ID_RE, _PASSPORT_RE, _RESIDENTIAL_ADDRESS_RE)
_DROP_FIELDS = {
	"idcard", "idnumber", "identitynumber", "身份证", "身份证号",
	"passport", "passportnumber", "passportno", "护照", "护照号", "护照号码",
	"address", "homeaddress", "residenceaddress", "residentialaddress",
	"住址", "家庭住址", "家庭地址", "现住址", "现居住址", "居住地址", "住宅地址", "详细住址",
}


def _canonical_field(value: Any) -> str:
	return _FIELD_NORMALIZER.sub("", str(value).casefold())


def _validated_job_key(value: Any) -> str:
	return _safe_storage_key(str(value or ""), label="job_key", max_length=128)


def contains_high_risk_identity_text(text: str) -> bool:
	"""Return whether text includes non-operational identity/address data."""
	return any(pattern.search(text) for pattern in _HIGH_RISK_PATTERNS)


def sanitize_high_risk_identity_text(text: str) -> str:
	"""Remove identity numbers/passports/residential addresses but keep operational contacts."""
	value = _CN_ID_RE.sub("[身份证号已移除]", text)
	value = _PASSPORT_RE.sub("[护照号已移除]", value)
	return _RESIDENTIAL_ADDRESS_RE.sub("[居住地址已移除]", value)


def sanitize_local_resume(resume: dict[str, Any]) -> dict[str, Any]:
	"""Return a cloned resume without non-operational identity/address data."""
	def clean(value: Any) -> Any:
		if isinstance(value, dict):
			result: dict[str, Any] = {}
			for key, child in value.items():
				if _canonical_field(key) in _DROP_FIELDS:
					continue
				result[str(key)] = clean(child)
			return result
		if isinstance(value, list):
			return [clean(item) for item in value]
		if isinstance(value, str):
			return sanitize_high_risk_identity_text(value)
		return value

	return cast("dict[str, Any]", clean(resume))


def install_local_data_safety(model_module: Any, store_cls: type[Any]) -> None:
	"""Apply the same high-risk-data policy to model input and direct Store writes."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True

	original_redact: Callable[[str], str] = model_module.redact_contact_text
	original_redact_resume: Callable[[dict[str, Any]], dict[str, Any]] = model_module.redact_resume_for_model
	original_find_unchanged: Callable[..., dict[str, Any] | None] = store_cls.find_unchanged
	original_save_evaluation: Callable[..., dict[str, Any]] = store_cls.save_evaluation
	original_save_reply: Callable[..., dict[str, Any]] = store_cls.save_reply

	def redact_contact_text(text: str) -> str:
		return sanitize_high_risk_identity_text(original_redact(text))

	def redact_resume_for_model(resume: dict[str, Any]) -> dict[str, Any]:
		return sanitize_local_resume(original_redact_resume(resume))

	def find_unchanged(self: Any, **kwargs: Any) -> dict[str, Any] | None:
		kwargs["job_key"] = _validated_job_key(kwargs.get("job_key"))
		resume = kwargs.get("resume")
		if isinstance(resume, dict):
			kwargs["resume"] = sanitize_local_resume(resume)
		return original_find_unchanged(self, **kwargs)

	def save_evaluation(self: Any, **kwargs: Any) -> dict[str, Any]:
		kwargs["job_key"] = _validated_job_key(kwargs.get("job_key"))
		resume = kwargs.get("resume")
		if isinstance(resume, dict):
			kwargs["resume"] = sanitize_local_resume(resume)
		return original_save_evaluation(self, **kwargs)

	def save_reply(self: Any, **kwargs: Any) -> dict[str, Any]:
		if "conversation" in kwargs:
			kwargs["conversation"] = sanitize_high_risk_identity_text(str(kwargs.get("conversation") or ""))
		return original_save_reply(self, **kwargs)

	model_module.redact_contact_text = redact_contact_text
	model_module.redact_resume_for_model = redact_resume_for_model
	setattr(store_cls, "find_unchanged", find_unchanged)
	setattr(store_cls, "save_evaluation", save_evaluation)
	setattr(store_cls, "save_reply", save_reply)
