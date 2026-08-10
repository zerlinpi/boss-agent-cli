"""Additional privacy and decision-safety guards for recruiter AI workflows."""

from __future__ import annotations

import re
from typing import Any, Callable, cast

_PROXY_RUBRIC_PATTERN = re.compile(
	r"(?:80|85|90|95|00)后(?:候选人|人选|人才|优先)?|"
	r"年轻(?:候选人|人选|人才|员工|男性|女性)|年轻\s*(?:优先|为佳|更佳|偏好)|"
	r"\byoung(?:er)?\s+(?:candidate|applicant|preferred)\b|"
	r"\b(?:under|below)\s*\d{1,2}\s*(?:years?\s*old|y/?o)\b|"
	r"\bborn\s+(?:after|before)\s+(?:19|20)\d{2}\b",
	re.IGNORECASE,
)

_VAGUE_PROTECTED_TEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
	(
		re.compile(
			r"(?:年龄|age)\s*(?:偏好|要求|限制|门槛|优先|加分|较大|较小|偏大|偏小)"
			r"\s*[:：]?\s*(?:不限|无|[<>≤≥]?\s*\d{1,3}\s*(?:岁|years?\s*old)?\s*(?:以下|以上|以内|以外)?)?",
			re.I,
		),
		"[年龄偏好已隔离]",
	),
	(
		re.compile(
			r"(?:性别|gender|sex)\s*(?:偏好|要求|限制|门槛|优先|加分)"
			r"\s*[:：]?\s*(?:不限|无|男性|女性|男|女|male|female)?",
			re.I,
		),
		"[性别偏好已隔离]",
	),
	(
		re.compile(
			r"(?:婚姻|婚育)\s*(?:偏好|要求|限制|门槛|优先|加分|稳定(?:性)?(?:\s*(?:优先|加分|更佳))?)"
			r"\s*[:：]?\s*(?:不限|无|已婚|未婚|离异|丧偶)?"
	),
		"[婚姻偏好已隔离]",
	),
	(
		re.compile(r"(?:你|您)?\s*(?:是否|有没有|有无)?\s*(?:结婚|婚否|婚姻情况|婚姻状态)(?:了|吗|呢)?"),
		"[婚姻问题已隔离]",
	),
	(
		re.compile(r"(?:你|您)?\s*(?:是否有|有没有|有无)\s*孩子(?:吗|呢)?|(?:你|您)?\s*有孩子吗"),
		"[家庭情况已隔离]",
	),
	(
		re.compile(r"(?:80|85|90|95|00)后(?:候选人|人选|人才|优先)?"),
		"[年龄代际已隔离]",
	),
	(
		re.compile(r"年轻(?:候选人|人选|人才|员工|男性|女性)|年轻\s*(?:优先|为佳|更佳|偏好)"),
		"[年龄偏好已隔离]",
	),
)

_DIMENSION_SEPARATORS_RE = re.compile(r"[^\w]+", re.UNICODE)
_REQUIREMENT_SPACE_RE = re.compile(r"\s+")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _dimension_key(value: Any) -> str:
	text = _CAMEL_BOUNDARY_RE.sub("_", str(value)).casefold()
	return _DIMENSION_SEPARATORS_RE.sub("_", text).strip("_")


def _requirement_key(value: Any) -> str:
	return _REQUIREMENT_SPACE_RE.sub(" ", str(value)).strip().casefold()


def _rubric_texts(payload: dict[str, Any]) -> list[tuple[str, str]]:
	items: list[tuple[str, str]] = []
	for key, label in (
		("instructions", "评分规则 instructions"),
		("title", "岗位标题"),
		("persona_summary", "岗位画像 persona_summary"),
	):
		value = payload.get(key)
		if value not in (None, ""):
			items.append((label, str(value)))
	for item in payload.get("dimensions", []) if isinstance(payload.get("dimensions"), list) else []:
		if isinstance(item, dict):
			items.append(("评分维度", f"{item.get('name', '')} {item.get('description', '')}"))
	for item in payload.get("hard_requirements", []) if isinstance(payload.get("hard_requirements"), list) else []:
		if isinstance(item, dict):
			items.append(("硬性要求", str(item.get("requirement", ""))))
		else:
			items.append(("硬性要求", str(item)))
	questions = payload.get("suggested_questions")
	if isinstance(questions, list):
		items.extend(("建议面试问题", str(question)) for question in questions)
	return items


def _redact_nested_strings(value: Any, sanitizer: Callable[[str], str]) -> Any:
	if isinstance(value, dict):
		for key in list(value):
			value[key] = _redact_nested_strings(value[key], sanitizer)
		return value
	if isinstance(value, list):
		for index, item in enumerate(value):
			value[index] = _redact_nested_strings(item, sanitizer)
		return value
	return sanitizer(value) if isinstance(value, str) else value


def install_model_and_store_hardening(model_module: Any, store_cls: type[Any]) -> None:
	"""Harden model input, rubric validation, and incremental invalidation."""
	if getattr(model_module, "_recruiter_privacy_hardening_installed", False):
		return

	original_redact: Callable[[str], str] = model_module.redact_contact_text
	original_redact_resume: Callable[[dict[str, Any]], dict[str, Any]] = model_module.redact_resume_for_model
	original_normalize_rubric: Callable[[dict[str, Any] | None], dict[str, Any]] = model_module.normalize_rubric
	original_find_unchanged: Callable[..., dict[str, Any] | None] = store_cls.find_unchanged

	def hardened_redact(text: str) -> str:
		redacted = original_redact(text)
		for pattern, replacement in _VAGUE_PROTECTED_TEXT_PATTERNS:
			redacted = pattern.sub(replacement, redacted)
		return redacted

	def hardened_redact_resume(resume: dict[str, Any]) -> dict[str, Any]:
		redacted = original_redact_resume(resume)
		return cast("dict[str, Any]", _redact_nested_strings(redacted, hardened_redact))

	def hardened_normalize_rubric(payload: dict[str, Any] | None = None) -> dict[str, Any]:
		raw = payload or {}
		for label, text in _rubric_texts(raw):
			if text and _PROXY_RUBRIC_PATTERN.search(text):
				raise model_module.RecruiterAIError(
					f"{label} 不能使用年龄代际或年轻化等个人属性代理条件"
				)

		dimensions = raw.get("dimensions")
		if isinstance(dimensions, list):
			seen_dimensions: set[str] = set()
			for item in dimensions:
				if not isinstance(item, dict):
					continue
				key = _dimension_key(item.get("name", ""))
				if not key:
					continue
				if key in seen_dimensions:
					raise model_module.RecruiterAIError("评分维度 name 归一化后不能重复")
				seen_dimensions.add(key)

		hard_requirements = raw.get("hard_requirements")
		if isinstance(hard_requirements, list):
			seen_requirements: set[str] = set()
			for item in hard_requirements:
				requirement = item.get("requirement", "") if isinstance(item, dict) else item
				key = _requirement_key(requirement)
				if not key:
					continue
				if key in seen_requirements:
					raise model_module.RecruiterAIError("硬性要求归一化后不能重复")
				seen_requirements.add(key)

		return original_normalize_rubric(raw)

	def hardened_find_unchanged(self: Any, **kwargs: Any) -> dict[str, Any] | None:
		record = original_find_unchanged(self, **kwargs)
		if record is None:
			return None
		job_key = str(kwargs.get("job_key") or "")
		if not job_key:
			return record
		try:
			job = self.get_job(job_key)
		except model_module.RecruiterAIError:
			return record
		current_jd = str(job.get("jd_text") or "") if isinstance(job, dict) else ""
		if current_jd and str(record.get("jd_text") or "") != current_jd:
			return None
		return record

	model_module.redact_contact_text = hardened_redact
	model_module.redact_resume_for_model = hardened_redact_resume
	model_module.normalize_rubric = hardened_normalize_rubric
	setattr(store_cls, "find_unchanged", hardened_find_unchanged)
	setattr(model_module, "_recruiter_privacy_hardening_installed", True)


def install_evaluation_output_hardening(evaluation_module: Any, model_module: Any) -> None:
	"""Drop unsafe model-invented evidence/questions before they can influence recruiter output."""
	if getattr(evaluation_module, "_recruiter_output_hardening_installed", False):
		return
	original_validate: Callable[..., dict[str, Any]] = evaluation_module.validate_evaluation

	# Keep evaluation matching aligned with rubric duplicate detection.
	evaluation_module._dimension_key = _dimension_key

	def sanitize_text(value: Any) -> tuple[str, bool]:
		text = str(value).strip()
		if not text:
			return "", False
		safe = model_module.redact_contact_text(text)
		return safe, safe != text

	def safe_list(value: Any, *, limit: int = 20) -> tuple[list[str], bool]:
		if not isinstance(value, list):
			return [], False
		result: list[str] = []
		changed = False
		for item in value:
			text, unsafe = sanitize_text(item)
			if unsafe:
				changed = True
				continue
			if text and text not in result:
				result.append(text)
			if len(result) >= limit:
				break
		return result, changed

	def hardened_validate(
		payload: dict[str, Any],
		rubric: dict[str, Any] | None = None,
	) -> dict[str, Any]:
		normalized_rubric = model_module.normalize_rubric(rubric)
		clean = cast("dict[str, Any]", model_module.json_clone(payload))
		flags: set[str] = set()

		for dimension in clean.get("dimensions", []) if isinstance(clean.get("dimensions"), list) else []:
			if not isinstance(dimension, dict):
				continue
			evidence, evidence_changed = safe_list(dimension.get("evidence", []))
			dimension["evidence"] = evidence
			reason, reason_changed = sanitize_text(dimension.get("reason", ""))
			dimension["reason"] = reason
			if evidence_changed or reason_changed:
				flags.add("protected_or_contact_content")

		configured_requirements = {
			_requirement_key(item.get("requirement", ""))
			for item in normalized_rubric.get("hard_requirements", [])
			if isinstance(item, dict) and _requirement_key(item.get("requirement", ""))
		}
		clean_hard: list[dict[str, Any]] = []
		for item in clean.get("hard_requirements", []) if isinstance(clean.get("hard_requirements"), list) else []:
			if not isinstance(item, dict):
				continue
			key = _requirement_key(item.get("requirement", ""))
			if not key or key not in configured_requirements:
				flags.add("unexpected_hard_requirement")
				continue
			evidence, evidence_changed = safe_list(item.get("evidence", []))
			item["evidence"] = evidence
			if evidence_changed:
				flags.add("protected_or_contact_content")
			clean_hard.append(item)
		clean["hard_requirements"] = clean_hard

		for key in ("strengths", "concerns", "next_questions"):
			items, items_changed = safe_list(clean.get(key, []), limit=20)
			clean[key] = items
			if items_changed:
				flags.add("protected_or_contact_content")

		summary, summary_changed = sanitize_text(clean.get("summary", ""))
		clean["summary"] = summary
		if summary_changed:
			flags.add("protected_or_contact_content")

		result = original_validate(clean, normalized_rubric)
		if flags:
			result["recommendation"] = "manual_review"
			result["model_output_sanitized"] = True
			result["model_output_safety_flags"] = sorted(flags)
		return result

	evaluation_module.validate_evaluation = hardened_validate
	setattr(evaluation_module, "_recruiter_output_hardening_installed", True)
