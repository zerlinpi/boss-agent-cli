"""Data normalization and configuration helpers for recruiter AI workflows."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, cast

from boss_agent_cli.commands.recruiter.resume_parser import parse_resume

SCHEMA_VERSION = "2.0"

PROTECTED_BASIC_FIELDS = {
	"age", "age_desc", "avatar", "birth_date", "birthday", "gender",
	"marital_status", "marriage", "nationality", "photo", "political_status",
}
CONTACT_FIELDS = {
	"address", "contact", "email", "home_address", "id_card", "id_number",
	"identity_number", "mobile", "phone", "phone_number", "qq",
	"residence_address", "wechat", "weixin",
}
RECOMMENDATIONS = {
	"strong_interview", "interview", "manual_review", "not_recommended",
}
CANDIDATE_STATUSES = {
	"new", "shortlisted", "interview", "hold", "rejected", "hired",
}
DEFAULT_DIMENSIONS: tuple[dict[str, Any], ...] = (
	{"name": "required_skills", "max_score": 30, "description": "岗位必需技能及熟练度的匹配程度"},
	{"name": "relevant_experience", "max_score": 20, "description": "与岗位职责直接相关的工作经历"},
	{"name": "project_evidence", "max_score": 15, "description": "项目复杂度、个人贡献和可验证细节"},
	{"name": "responsibility_match", "max_score": 15, "description": "历史职责与目标岗位日常工作的匹配度"},
	{"name": "industry_match", "max_score": 10, "description": "业务领域和行业经验的可迁移程度"},
	{"name": "achievement_evidence", "max_score": 10, "description": "成果、规模、效率、质量等量化证据"},
)
DEFAULT_THRESHOLDS = {"strong_interview": 85, "interview": 70, "manual_review": 50}

_ID_KEYS = ("geekId", "geek_id", "encryptGeekId", "encryptUid", "uid")
_SECURITY_KEYS = ("securityId", "security_id", "geekSecurityId", "encryptSecurityId")
_JOB_KEYS = ("jobId", "job_id", "encJobId", "encryptJobId")
_FRIEND_KEYS = ("friendId", "friend_id", "uid", "gid")
_NAME_KEYS = ("name", "geekName", "candidateName")
_LIST_KEYS = ("friendList", "geekList", "applications", "items", "list", "result")


class RecruiterAIError(ValueError):
	"""Raised when recruiter AI input, configuration, or output is invalid."""


def json_clone(value: Any) -> Any:
	return json.loads(json.dumps(value, ensure_ascii=False))


def stable_hash(value: Any) -> str:
	encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
	return hashlib.sha256(encoded).hexdigest()


def read_text_input(value: str) -> str:
	"""Read inline text or ``@path`` text input."""
	if not value.startswith("@"):
		text = value.strip()
		if not text:
			raise RecruiterAIError("输入文本不能为空")
		return text
	path = Path(value[1:]).expanduser()
	if not path.is_file():
		raise RecruiterAIError(f"文件不存在: {path}")
	text = path.read_text(encoding="utf-8").strip()
	if not text:
		raise RecruiterAIError(f"文件内容为空: {path}")
	return text


def read_json_input(value: str) -> dict[str, Any]:
	"""Read inline JSON or ``@path`` JSON input."""
	try:
		payload = json.loads(read_text_input(value))
	except json.JSONDecodeError as exc:
		raise RecruiterAIError(f"JSON 解析失败: {exc.msg}") from exc
	if not isinstance(payload, dict):
		raise RecruiterAIError("JSON 顶层必须是对象")
	return cast("dict[str, Any]", payload)


def parse_ai_json(raw: str) -> dict[str, Any]:
	"""Parse a model response, tolerating fenced JSON and leading prose."""
	text = raw.strip()
	if text.startswith("```"):
		text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
		text = re.sub(r"\s*```$", "", text)
	if not text.startswith("{"):
		start, end = text.find("{"), text.rfind("}")
		if start >= 0 and end > start:
			text = text[start:end + 1]
	try:
		payload = json.loads(text)
	except json.JSONDecodeError as exc:
		raise RecruiterAIError(f"AI 返回结果不是有效 JSON: {exc.msg}") from exc
	if not isinstance(payload, dict):
		raise RecruiterAIError("AI 返回 JSON 顶层必须是对象")
	return cast("dict[str, Any]", payload)


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
			if key.lower() in fields:
				value.pop(key, None)
			else:
				_strip_fields(value[key], fields)
	elif isinstance(value, list):
		for item in value:
			_strip_fields(item, fields)


def _redact_text_values(value: Any, *, identity: str) -> Any:
	"""Recursively redact contact details and the candidate name from free text."""
	if isinstance(value, dict):
		for key in list(value):
			value[key] = _redact_text_values(value[key], identity=identity)
		return value
	if isinstance(value, list):
		for index, item in enumerate(value):
			value[index] = _redact_text_values(item, identity=identity)
		return value
	if not isinstance(value, str):
		return value
	text = redact_contact_text(value)
	if len(identity) >= 2 and identity != "candidate":
		text = text.replace(identity, "[姓名已脱敏]")
	return text


def normalize_resume(payload: dict[str, Any]) -> dict[str, Any]:
	"""Unwrap CLI envelopes, parse raw BOSS payloads, and remove protected data."""
	data: dict[str, Any] = payload
	if payload.get("ok") is True and isinstance(payload.get("data"), dict):
		data = cast("dict[str, Any]", payload["data"])
	data = parse_resume(data) if _looks_like_raw_boss_resume(data) else cast("dict[str, Any]", json_clone(data))
	_strip_fields(data, {field.lower() for field in PROTECTED_BASIC_FIELDS | CONTACT_FIELDS})
	return data


def redact_resume_for_model(resume: dict[str, Any]) -> dict[str, Any]:
	"""Create a model payload without identity, contact, or protected fields."""
	identity = candidate_name(resume, fallback="")
	redacted = cast("dict[str, Any]", json_clone(resume))
	_strip_fields(
		redacted,
		{field.lower() for field in PROTECTED_BASIC_FIELDS | CONTACT_FIELDS | {"name", "candidate_name"}},
	)
	_redact_text_values(redacted, identity=identity)
	basic = redacted.get("basic")
	if isinstance(basic, dict):
		basic["name"] = "candidate"
	return redacted


def redact_contact_text(text: str) -> str:
	text = re.sub(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d(?:[- ]?\d){8}(?!\d)", "[手机号已脱敏]", text)
	text = re.sub(r"(?<!\d)0\d{2,3}[- ]?\d{7,8}(?!\d)", "[座机已脱敏]", text)
	text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[邮箱已脱敏]", text)
	text = re.sub(r"(?<!\d)\d{17}[\dXx](?!\d)|(?<!\d)\d{15}(?!\d)", "[身份证号已脱敏]", text)
	text = re.sub(r"(?:QQ|qq)\s*[:：]?\s*[1-9]\d{4,11}", "[QQ 已脱敏]", text)
	return re.sub(r"(?:微信|微信号|wechat|weixin)\s*[:：]?\s*[A-Za-z0-9_-]{5,}", "[微信已脱敏]", text, flags=re.I)


def candidate_name(resume: dict[str, Any], *, fallback: str = "candidate") -> str:
	basic = resume.get("basic")
	if isinstance(basic, dict):
		name = basic.get("name")
		if isinstance(name, str) and name.strip():
			return name.strip()
	name = resume.get("name")
	return name.strip() if isinstance(name, str) and name.strip() else fallback


def resume_fingerprint(resume: dict[str, Any]) -> str:
	return stable_hash(redact_resume_for_model(resume))


def candidate_key(resume: dict[str, Any], source: dict[str, Any] | None = None) -> str:
	source = source or {}
	for key in ("friend_id", "geek_id", "candidate_id"):
		value = source.get(key)
		if value not in (None, ""):
			return f"{source.get('type', 'candidate')}:{value}"
	payload = {"name": candidate_name(resume), "resume": redact_resume_for_model(resume)}
	return f"local:{stable_hash(payload)[:24]}"


def _positive_integer(value: Any, *, label: str) -> int:
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		raise RecruiterAIError(f"{label} 必须是正整数")
	number = float(value)
	if not math.isfinite(number) or not number.is_integer() or number <= 0:
		raise RecruiterAIError(f"{label} 必须是正整数")
	return int(number)


def _threshold_integer(value: Any, *, label: str) -> int:
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		raise RecruiterAIError(f"{label} 必须是 0-100 的整数")
	number = float(value)
	if not math.isfinite(number) or not number.is_integer() or not 0 <= number <= 100:
		raise RecruiterAIError(f"{label} 必须是 0-100 的整数")
	return int(number)


def _max_questions(value: Any) -> int:
	if isinstance(value, bool):
		raise RecruiterAIError("max_questions 必须是 1-10 的整数")
	try:
		number = float(value)
	except (TypeError, ValueError) as exc:
		raise RecruiterAIError("max_questions 必须是 1-10 的整数") from exc
	if not math.isfinite(number) or not number.is_integer():
		raise RecruiterAIError("max_questions 必须是 1-10 的整数")
	return max(1, min(10, int(number)))


def normalize_rubric(payload: dict[str, Any] | None = None) -> dict[str, Any]:
	"""Normalize a configurable scoring rubric into a strict local contract."""
	payload = payload or {}
	dimensions_input = payload.get("dimensions", list(DEFAULT_DIMENSIONS))
	if not isinstance(dimensions_input, list) or not dimensions_input:
		raise RecruiterAIError("评分规则 dimensions 必须是非空列表")
	dimensions: list[dict[str, Any]] = []
	seen: set[str] = set()
	for item in dimensions_input:
		if not isinstance(item, dict):
			raise RecruiterAIError("每个评分维度必须是对象")
		name = str(item.get("name", "")).strip()
		if not name or name in seen:
			raise RecruiterAIError("评分维度 name 不能为空且不能重复")
		max_score = _positive_integer(item.get("max_score"), label=f"评分维度 {name} 的 max_score")
		seen.add(name)
		dimensions.append({
			"name": name,
			"max_score": max_score,
			"description": str(item.get("description", "")).strip(),
		})

	thresholds = dict(DEFAULT_THRESHOLDS)
	raw_thresholds = payload.get("thresholds")
	if raw_thresholds is not None and not isinstance(raw_thresholds, dict):
		raise RecruiterAIError("thresholds 必须是对象")
	if isinstance(raw_thresholds, dict):
		for key in thresholds:
			if key in raw_thresholds:
				thresholds[key] = _threshold_integer(raw_thresholds[key], label=f"评分阈值 {key}")
	if not 0 <= thresholds["manual_review"] <= thresholds["interview"] <= thresholds["strong_interview"] <= 100:
		raise RecruiterAIError("评分阈值必须满足 manual_review <= interview <= strong_interview")

	hard_requirements = payload.get("hard_requirements", [])
	if not isinstance(hard_requirements, list):
		raise RecruiterAIError("hard_requirements 必须是列表")
	normalized_hard: list[dict[str, Any]] = []
	seen_hard: set[str] = set()
	for item in hard_requirements:
		requirement = ""
		required = True
		if isinstance(item, str):
			requirement = item.strip()
		elif isinstance(item, dict):
			requirement = str(item.get("requirement", "")).strip()
			required = bool(item.get("required", True))
		if not requirement or requirement in seen_hard:
			continue
		seen_hard.add(requirement)
		normalized_hard.append({"requirement": requirement, "required": required})

	return {
		"version": str(payload.get("version") or "1"),
		"dimensions": dimensions,
		"thresholds": thresholds,
		"hard_requirements": normalized_hard,
		"instructions": str(payload.get("instructions", "")).strip(),
		"max_questions": _max_questions(payload.get("max_questions", 4)),
	}


def rubric_fingerprint(rubric: dict[str, Any]) -> str:
	return stable_hash(normalize_rubric(rubric))


def _first_value(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
	for key in keys:
		value = item.get(key)
		if value not in (None, ""):
			return value
	for nested_key in ("geekCard", "geekInfo", "geekBaseInfo", "candidate", "jobCard", "jobInfo"):
		nested = item.get(nested_key)
		if isinstance(nested, dict):
			value = _first_value(nested, keys)
			if value not in (None, ""):
				return value
	return None


def candidate_items(payload: Any) -> list[dict[str, Any]]:
	if isinstance(payload, list):
		return [item for item in payload if isinstance(item, dict)]
	if not isinstance(payload, dict):
		return []
	for envelope in ("data", "zpData"):
		value = payload.get(envelope)
		if isinstance(value, (dict, list)) and (items := candidate_items(value)):
			return items
	for key in _LIST_KEYS:
		value = payload.get(key)
		if isinstance(value, list):
			return [item for item in value if isinstance(item, dict)]
	return []


def extract_candidate_ref(item: dict[str, Any], *, default_job_id: str | None = None) -> dict[str, Any]:
	return {
		"name": str(_first_value(item, _NAME_KEYS) or "candidate"),
		"geek_id": str(_first_value(item, _ID_KEYS) or ""),
		"security_id": str(_first_value(item, _SECURITY_KEYS) or ""),
		"job_id": str(_first_value(item, _JOB_KEYS) or default_job_id or ""),
		"friend_id": _first_value(item, _FRIEND_KEYS),
		"raw": item,
	}


def conversation_to_text(payload: Any) -> str:
	if isinstance(payload, dict):
		for envelope in ("data", "zpData"):
			if envelope in payload:
				return conversation_to_text(payload[envelope])
		for key in ("messages", "messageList", "list", "result"):
			if isinstance(payload.get(key), list):
				return conversation_to_text(payload[key])
	if not isinstance(payload, list):
		return ""
	lines: list[str] = []
	for item in payload:
		if not isinstance(item, dict):
			continue
		content = _first_value(item, ("content", "text", "message", "msgContent"))
		if content in (None, ""):
			continue
		sender = item.get("from")
		sender_text = (
			str(sender.get("name") or sender.get("type") or "unknown")
			if isinstance(sender, dict)
			else str(item.get("sender") or item.get("direction") or "unknown")
		)
		lines.append(f"{sender_text}: {content}")
	return "\n".join(lines)
