"""Retain recruiter contact data locally while isolating it from model decisions."""

from __future__ import annotations

import re
from typing import Any, cast

import boss_agent_cli.recruiter_ai_models as model_module
from boss_agent_cli.commands.recruiter.resume_parser import parse_resume
from boss_agent_cli.recruiter_ai_store import RecruiterAIStore as BaseRecruiterAIStore
from boss_agent_cli.recruiter_reply_safety import scan_reply_safety

_LOCAL_CONTACT_FIELDS = {
	"contact", "email", "mobile", "phone", "phone_number", "qq", "wechat", "weixin",
}
_EXTRA_LOCAL_CONTACT_FIELDS = {"联系方式", "邮箱", "手机", "手机号", "电话", "微信", "微信号"}
_EXTRA_PROTECTED_FIELDS = {
	"sex", "sex_desc", "race", "ethnicity", "religion", "religious_affiliation",
	"health", "health_status", "disability", "pregnancy", "pregnancy_status",
	"fertility", "fertility_status", "family_status", "political_affiliation", "party_membership",
	"年龄", "性别", "婚姻", "婚姻状况", "出生日期", "生日", "民族", "国籍", "政治面貌",
	"政治身份", "党派", "宗教", "健康", "健康状况", "残疾", "残障", "怀孕", "孕期",
	"生育", "生育状况", "生育计划",
}
_IDENTITY_FIELDS = {"name", "candidate_name", "geek_name", "姓名", "候选人姓名"}
_NON_OPERATIONAL_LOCAL_FIELDS = (
	model_module.CONTACT_FIELDS - _LOCAL_CONTACT_FIELDS
) | {
	"idcard", "idnumber", "identitynumber", "身份证", "身份证号",
	"address", "homeaddress", "residenceaddress", "住址", "家庭住址", "详细地址",
}
_MODEL_DROP_FIELDS = (
	model_module.PROTECTED_BASIC_FIELDS
	| model_module.CONTACT_FIELDS
	| _EXTRA_PROTECTED_FIELDS
	| _EXTRA_LOCAL_CONTACT_FIELDS
	| _IDENTITY_FIELDS
)

_BASE_REDACT_CONTACT = model_module.redact_contact_text
_BASE_REDACT_RESUME = model_module.redact_resume_for_model

_PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d(?:[- ]?\d){8}(?!\d)")
_LANDLINE_RE = re.compile(r"(?<!\d)0\d{2,3}[- ]?\d{7,8}(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_WECHAT_RE = re.compile(r"(?:微信|微信号|wechat|weixin)\s*[:：]?\s*([A-Za-z0-9_-]{5,})", re.I)
_QQ_RE = re.compile(r"(?:QQ|qq)\s*[:：]?\s*([1-9]\d{4,11})")
_ID_NUMBER_RE = re.compile(r"(?<!\d)(?:\d{17}[\dXx]|\d{15})(?!\d)")
_FIELD_NORMALIZER = re.compile(r"[^a-z0-9\u4e00-\u9fff]+")

_PROTECTED_TEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
	(
		re.compile(
			r"(?:婚姻状况|婚姻|marital\s*status)\s*[:：]?\s*"
			r"(?:已婚|未婚|离异|丧偶|married|single|divorced|widowed)",
			re.I,
		),
		"[婚姻状况已隔离]",
	),
	(re.compile(r"(?:已婚|未婚|离异|丧偶)"), "[婚姻状况已隔离]"),
	(re.compile(r"(?:年龄|age)\s*[:：]?\s*\d{1,3}\s*(?:岁|years?\s*old)?", re.I), "[年龄已隔离]"),
	(re.compile(r"(?<!\d)(?:1[6-9]|[2-6]\d)\s*岁(?!\d)"), "[年龄已隔离]"),
	(re.compile(r"(?<!\d)(?:1[6-9]|[2-6]\d)\s*years?\s*old\b", re.I), "[年龄已隔离]"),
	(re.compile(r"(?:性别|gender|sex)\s*[:：]?\s*(?:男|女|male|female)", re.I), "[性别已隔离]"),
	(re.compile(r"(^|[\s|｜,，;；/])(?:男|女)(?=$|[\s|｜,，;；/])", re.M), r"\1[性别已隔离]"),
	(re.compile(r"\b(?:male|female)\b", re.I), "[性别已隔离]"),
	(
		re.compile(
			r"(?:出生日期|生日|birth(?:day|\s*date)?)\s*[:：]?\s*"
			r"\d{2,4}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?",
			re.I,
		),
		"[出生日期已隔离]",
	),
	(re.compile(r"(?:出生于\s*)?(?:19|20)\d{2}\s*年\s*出生"), "[出生日期已隔离]"),
	(re.compile(r"(?:民族|ethnicity|race)\s*[:：]?\s*[^,，;；\n]{1,20}", re.I), "[民族信息已隔离]"),
	(re.compile(r"(?:国籍|nationality)\s*[:：]?\s*[^,，;；\n]{1,20}", re.I), "[国籍信息已隔离]"),
	(re.compile(r"(?:政治面貌|政治身份|党派|political\s*(?:status|affiliation)|party\s*membership)\s*[:：]?\s*[^,，;；\n]{1,30}", re.I), "[政治面貌已隔离]"),
	(re.compile(r"(?:中共党员|共产党员|共青团员|民主党派成员)"), "[政治面貌已隔离]"),
	(re.compile(r"(?:宗教|religion|religious\s*affiliation)\s*[:：]?\s*[^,，;；\n]{1,30}", re.I), "[宗教信息已隔离]"),
	(re.compile(r"(?:佛教徒|基督徒|天主教徒|穆斯林|道教徒)"), "[宗教信息已隔离]"),
	(re.compile(r"(?:健康状况|health\s*status)\s*[:：]?\s*[^,，;；\n]{1,40}", re.I), "[健康信息已隔离]"),
	(re.compile(r"(?:残疾状况|残障状况|disability)\s*[:：]?\s*[^,，;；\n]{1,40}", re.I), "[残障信息已隔离]"),
	(re.compile(r"(?:残疾|残障|视力障碍|听力障碍)"), "[残障信息已隔离]"),
	(
		re.compile(
			r"(?:怀孕情况|孕期|生育状况|生育计划|pregnancy\s*status|fertility\s*status)"
			r"\s*[:：]?\s*[^,，;；\n]{1,40}",
			re.I,
		),
		"[孕育信息已隔离]",
	),
	(
		re.compile(
			r"(?:已育|未育|备孕|怀孕|孕妇|育有[一二三四五六七八九十\d]+(?:子|女|个?孩子)|"
			r"有[一二三四五六七八九十\d]+个孩子)",
		),
		"[孕育信息已隔离]",
	),
)


def _canonical_field(value: str) -> str:
	return _FIELD_NORMALIZER.sub("", value.casefold())


def _canonical_fields(fields: set[str]) -> set[str]:
	return {_canonical_field(field) for field in fields}


_LOCAL_DROP_CANONICAL = _canonical_fields(_NON_OPERATIONAL_LOCAL_FIELDS)
_MODEL_DROP_CANONICAL = _canonical_fields(_MODEL_DROP_FIELDS)
_CONTACT_KEY_MAP = {
	_canonical_field(key): kind
	for kind, keys in {
		"phone": {"phone", "phone_number", "mobile", "手机", "手机号", "电话"},
		"email": {"email", "邮箱"},
		"wechat": {"wechat", "weixin", "微信", "微信号"},
		"qq": {"qq"},
	}.items()
	for key in keys
}


def _looks_like_raw_boss_resume(payload: dict[str, Any]) -> bool:
	if "geekDetailInfo" in payload:
		return True
	return any(
		isinstance(payload.get(key), dict) and "geekDetailInfo" in payload[key]
		for key in ("data", "zpData")
	)


def _strip_fields(value: Any, fields: set[str]) -> None:
	if isinstance(value, dict):
		for key in list(value):
			if _canonical_field(str(key)) in fields:
				value.pop(key, None)
			else:
				_strip_fields(value[key], fields)
	elif isinstance(value, list):
		for item in value:
			_strip_fields(item, fields)


def _remove_non_operational_identifiers(value: Any) -> Any:
	"""Drop identity numbers from locally stored free text while keeping recruiter contact methods."""
	if isinstance(value, dict):
		for key in list(value):
			value[key] = _remove_non_operational_identifiers(value[key])
		return value
	if isinstance(value, list):
		for index, item in enumerate(value):
			value[index] = _remove_non_operational_identifiers(item)
		return value
	if isinstance(value, str):
		return _ID_NUMBER_RE.sub("[身份证号已移除]", value)
	return value


def normalize_resume(payload: dict[str, Any]) -> dict[str, Any]:
	"""Normalize a resume while retaining recruiter-useful local fields and contact methods."""
	data: dict[str, Any] = payload
	if payload.get("ok") is True and isinstance(payload.get("data"), dict):
		data = cast("dict[str, Any]", payload["data"])
	data = parse_resume(data) if _looks_like_raw_boss_resume(data) else cast(
		"dict[str, Any]", model_module.json_clone(data)
	)
	# Keep resume facts locally for the human recruiter, but remove identity numbers and full addresses.
	_strip_fields(data, _LOCAL_DROP_CANONICAL)
	return cast("dict[str, Any]", _remove_non_operational_identifiers(data))


def redact_text_for_model(text: str) -> str:
	"""Remove contact and protected-trait text before sending content to a model."""
	redacted = _BASE_REDACT_CONTACT(text)
	redacted = _LANDLINE_RE.sub("[座机已脱敏]", redacted)
	for pattern, replacement in _PROTECTED_TEXT_PATTERNS:
		redacted = pattern.sub(replacement, redacted)
	return redacted


def _redact_protected_text_values(value: Any) -> Any:
	if isinstance(value, dict):
		for key in list(value):
			value[key] = _redact_protected_text_values(value[key])
		return value
	if isinstance(value, list):
		for index, item in enumerate(value):
			value[index] = _redact_protected_text_values(item)
		return value
	return redact_text_for_model(value) if isinstance(value, str) else value


def redact_resume_for_model(resume: dict[str, Any]) -> dict[str, Any]:
	"""Create a model-safe resume while the locally stored resume keeps recruiter-useful data."""
	redacted = _BASE_REDACT_RESUME(resume)
	# Base redaction historically matched snake_case keys exactly. Re-run using canonical keys so
	# camelCase, Chinese labels, and common aliases cannot leak structured protected fields.
	_strip_fields(redacted, _MODEL_DROP_CANONICAL)
	return cast("dict[str, Any]", _redact_protected_text_values(redacted))


def install_model_sanitizer() -> None:
	"""Install model-only sanitizers before evaluation helpers bind their imports."""
	if getattr(model_module, "_local_contact_retention_installed", False):
		return
	model_module.redact_contact_text = redact_text_for_model
	model_module.redact_resume_for_model = redact_resume_for_model
	setattr(model_module, "_local_contact_retention_installed", True)


def extract_contact_details(resume: dict[str, Any]) -> dict[str, list[str]]:
	"""Extract operational contact methods from structured fields and resume text."""
	contacts: dict[str, list[str]] = {"phone": [], "email": [], "wechat": [], "qq": []}

	def add(kind: str, value: str) -> None:
		text = value.strip()
		if not text:
			return
		values: list[str]
		if kind == "phone":
			values = _PHONE_RE.findall(text) + _LANDLINE_RE.findall(text)
			if not values and re.fullmatch(r"[+\d][\d\- ]{6,20}", text):
				values = [text]
		elif kind == "email":
			values = _EMAIL_RE.findall(text)
			if not values and "@" in text:
				values = [text]
		elif kind == "wechat":
			matched = [match.group(1) for match in _WECHAT_RE.finditer(text)]
			values = matched or ([text] if re.fullmatch(r"[A-Za-z0-9_-]{5,}", text) else [])
		else:
			matched = [match.group(1) for match in _QQ_RE.finditer(text)]
			values = matched or ([text] if re.fullmatch(r"[1-9]\d{4,11}", text) else [])
		for item in values:
			item = item.strip()
			if item and item not in contacts[kind] and len(contacts[kind]) < 10:
				contacts[kind].append(item)

	def walk(value: Any) -> None:
		if isinstance(value, dict):
			for child_key, child in value.items():
				kind = _CONTACT_KEY_MAP.get(_canonical_field(str(child_key)))
				if kind and isinstance(child, (str, int, float)):
					add(kind, str(child))
				walk(child)
			return
		if isinstance(value, list):
			for item in value:
				walk(item)
			return
		if not isinstance(value, str):
			return
		for match in _PHONE_RE.findall(value) + _LANDLINE_RE.findall(value):
			add("phone", match)
		for match in _EMAIL_RE.findall(value):
			add("email", match)
		for match in _WECHAT_RE.finditer(value):
			add("wechat", match.group(1))
		for match in _QQ_RE.finditer(value):
			add("qq", match.group(1))

	walk(resume)
	return contacts


class RecruiterAIStore(BaseRecruiterAIStore):
	"""Store contacts locally without changing the model-safe screening payload."""

	def save_evaluation(self, **kwargs: Any) -> dict[str, Any]:
		record = super().save_evaluation(**kwargs)
		resume = kwargs.get("resume")
		if isinstance(resume, dict):
			record["contacts"] = extract_contact_details(resume)
			self._write(self.evaluations_dir / f"{record['id']}.json", record)
		return record

	def get_evaluation(self, record_id: str) -> dict[str, Any]:
		record = super().get_evaluation(record_id)
		if "contacts" not in record and isinstance(record.get("resume"), dict):
			record["contacts"] = extract_contact_details(cast("dict[str, Any]", record["resume"]))
		return record

	def save_reply(
		self,
		*,
		evaluation_id: str,
		intent: str,
		conversation: str,
		draft: dict[str, Any],
	) -> dict[str, Any]:
		record = super().save_reply(
			evaluation_id=evaluation_id,
			intent=intent,
			conversation=conversation,
			draft=draft,
		)
		record["conversation"] = conversation
		record["local_contact_retained"] = True
		stored_draft = record.get("draft")
		if isinstance(stored_draft, dict):
			flags = scan_reply_safety(str(stored_draft.get("reply") or ""))
			stored_draft["safety_flags"] = flags
			stored_draft["prohibited_content_detected"] = bool(
				stored_draft.get("prohibited_content_detected") or flags
			)
		record["requires_human_review"] = True
		self._write(self.replies_dir / f"{record['id']}.json", record)
		return record
