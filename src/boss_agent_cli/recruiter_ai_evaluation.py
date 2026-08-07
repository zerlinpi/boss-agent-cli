"""Evidence-backed scoring and recruiter reply drafting."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from boss_agent_cli.ai.service import ChatService
from boss_agent_cli.recruiter_ai_models import (
	RecruiterAIError,
	candidate_name,
	json_clone,
	normalize_rubric,
	parse_ai_json,
	redact_contact_text,
	redact_resume_for_model,
)


def build_evaluation_messages(
	jd_text: str,
	resume: dict[str, Any],
	rubric: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
	normalized_rubric = normalize_rubric(rubric)
	payload = {
		"job_description": redact_contact_text(jd_text),
		"resume": redact_resume_for_model(resume),
		"rubric": normalized_rubric,
		"output_schema": {
			"total_score": "number 0-100; derived from dimensions",
			"recommendation": "strong_interview|interview|manual_review|not_recommended",
			"confidence": "number 0-1",
			"hard_requirements": [
				{"requirement": "string", "status": "met|missing|unclear", "evidence": ["string"]}
			],
			"dimensions": [{
				"name": "one of rubric.dimensions.name",
				"score": "finite number between 0 and max_score",
				"max_score": "must equal rubric dimension max_score",
				"reason": "string",
				"evidence": ["concise resume facts; positive score requires evidence"],
			}],
			"strengths": ["string"], "concerns": ["string"],
			"next_questions": ["string"], "summary": "string",
		},
	}
	return [
		{
			"role": "system",
			"content": (
				"你是招聘筛选助手。仅依据岗位相关能力和简历中的可验证证据评分。"
				"不得依据性别、年龄、照片、婚育、民族、健康、政治面貌等受保护属性做判断；"
				"信息不足必须标记 unclear，不得推断。每个正分维度和标记为 met 的硬性要求都必须提供证据。"
				"所有分数和置信度必须是有限数字，不得输出 NaN 或 Infinity。"
				"AI 只提供辅助建议，不作最终录用或淘汰决定。严格输出一个 JSON 对象。"
			),
		},
		{"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
	]


def _as_text_list(value: Any, *, limit: int = 20) -> list[str]:
	if not isinstance(value, list):
		return []
	items: list[str] = []
	for item in value:
		text = str(item).strip()
		if text and text not in items:
			items.append(text)
		if len(items) >= limit:
			break
	return items


def _finite_number(value: Any, *, default: float) -> float:
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		return default
	number = float(value)
	return number if math.isfinite(number) else default


def _dimension_key(value: Any) -> str:
	return re.sub(r"[\s\-]+", "_", str(value)).strip("_").casefold()


def _requirement_key(value: Any) -> str:
	return re.sub(r"\s+", " ", str(value)).strip().casefold()


def _recommendation_for(
	score: int,
	thresholds: dict[str, int],
	*,
	hard_missing: bool,
	hard_unclear: bool,
) -> str:
	if hard_missing or hard_unclear:
		return "manual_review"
	if score >= thresholds["strong_interview"]:
		return "strong_interview"
	if score >= thresholds["interview"]:
		return "interview"
	if score >= thresholds["manual_review"]:
		return "manual_review"
	return "not_recommended"


def validate_evaluation(
	payload: dict[str, Any],
	rubric: dict[str, Any] | None = None,
) -> dict[str, Any]:
	"""Normalize model output and recompute evidence-backed scores locally."""
	normalized_rubric = normalize_rubric(rubric)
	dimension_specs = {_dimension_key(item["name"]): item for item in normalized_rubric["dimensions"]}
	raw_dimensions = payload.get("dimensions")
	if not isinstance(raw_dimensions, list):
		raise RecruiterAIError("AI 结果缺少 dimensions 列表")
	raw_by_name: dict[str, dict[str, Any]] = {}
	for item in raw_dimensions:
		if not isinstance(item, dict) or item.get("name") is None:
			continue
		key = _dimension_key(item.get("name"))
		if key:
			raw_by_name[key] = item
	dimensions: list[dict[str, Any]] = []
	total_points = 0.0
	max_points = 0.0
	for key, spec in dimension_specs.items():
		name = str(spec["name"])
		item = raw_by_name.get(key, {})
		raw_score = item.get("score", 0) if isinstance(item, dict) else 0
		max_score = float(spec["max_score"])
		evidence = _as_text_list(item.get("evidence", []) if isinstance(item, dict) else [])
		score = max(0.0, min(max_score, _finite_number(raw_score, default=0.0)))
		if score > 0 and not evidence:
			score = 0.0
		total_points += score
		max_points += max_score
		dimensions.append({
			"name": name,
			"score": round(score, 2),
			"max_score": int(max_score),
			"reason": str(item.get("reason", "")).strip() if isinstance(item, dict) else "",
			"evidence": evidence,
		})
	if max_points <= 0 or not math.isfinite(max_points):
		raise RecruiterAIError("评分规则总分必须是大于 0 的有限数字")
	total_score = int(round(total_points / max_points * 100))

	configured_hard = normalized_rubric["hard_requirements"]
	configured_names = {
		_requirement_key(item["requirement"]): item["requirement"]
		for item in configured_hard
		if _requirement_key(item["requirement"])
	}
	hard_results: list[dict[str, Any]] = []
	for item in payload.get("hard_requirements", []):
		if not isinstance(item, dict):
			continue
		requirement = str(item.get("requirement", "")).strip()
		key = _requirement_key(requirement)
		if not key:
			continue
		status = str(item.get("status", "unclear")).lower()
		if status not in {"met", "missing", "unclear"}:
			status = "unclear"
		evidence = _as_text_list(item.get("evidence", []))
		if status == "met" and not evidence:
			status = "unclear"
		hard_results.append({
			"requirement": configured_names.get(key, requirement),
			"status": status,
			"evidence": evidence,
		})
	by_requirement = {_requirement_key(item["requirement"]): item for item in hard_results}
	for spec in configured_hard:
		key = _requirement_key(spec["requirement"])
		if key not in by_requirement:
			hard_results.append({"requirement": spec["requirement"], "status": "unclear", "evidence": []})
	required_keys = {
		_requirement_key(item["requirement"])
		for item in configured_hard
		if item.get("required", True)
	}
	hard_missing = any(
		item["status"] == "missing" and _requirement_key(item["requirement"]) in required_keys
		for item in hard_results
	)
	hard_unclear = any(
		item["status"] == "unclear" and _requirement_key(item["requirement"]) in required_keys
		for item in hard_results
	)

	confidence = round(max(0.0, min(1.0, _finite_number(payload.get("confidence", 0.5), default=0.5))), 3)
	evidenced_dimensions = sum(1 for item in dimensions if item["evidence"])
	evidence_coverage = round(evidenced_dimensions / len(dimensions), 3) if dimensions else 0.0
	return {
		"total_score": total_score,
		"recommendation": _recommendation_for(
			total_score,
			normalized_rubric["thresholds"],
			hard_missing=hard_missing,
			hard_unclear=hard_unclear,
		),
		"confidence": confidence,
		"evidence_coverage": evidence_coverage,
		"hard_requirements": hard_results,
		"dimensions": dimensions,
		"strengths": _as_text_list(payload.get("strengths", [])),
		"concerns": _as_text_list(payload.get("concerns", [])),
		"next_questions": _as_text_list(
			payload.get("next_questions", []), limit=normalized_rubric["max_questions"]
		),
		"summary": str(payload.get("summary", "")).strip(),
		"human_review_required": True,
		"score_source": "evidence_backed_dimension_sum",
	}


def evaluate_resume(
	service: ChatService,
	jd_text: str,
	resume: dict[str, Any],
	rubric: dict[str, Any] | None = None,
) -> dict[str, Any]:
	normalized_rubric = normalize_rubric(rubric)
	raw = service.chat(build_evaluation_messages(jd_text, resume, normalized_rubric), temperature=0.1)
	result = validate_evaluation(parse_ai_json(raw), normalized_rubric)
	result["candidate_name"] = candidate_name(resume)
	return result


def recommended_reply_intent(evaluation: dict[str, Any]) -> str:
	questions = evaluation.get("next_questions")
	if isinstance(questions, list) and questions:
		return "ask_followup"
	if evaluation.get("recommendation") in {"strong_interview", "interview"}:
		return "invite_interview"
	if evaluation.get("recommendation") == "manual_review":
		return "clarify"
	return "decline_draft"


def _redact_reply_value(value: Any, *, identity: str) -> Any:
	if isinstance(value, dict):
		for key in list(value):
			value[key] = _redact_reply_value(value[key], identity=identity)
		return value
	if isinstance(value, list):
		for index, item in enumerate(value):
			value[index] = _redact_reply_value(item, identity=identity)
		return value
	if not isinstance(value, str):
		return value
	text = redact_contact_text(value)
	if len(identity) >= 2:
		text = text.replace(identity, "[姓名已脱敏]")
	return text


def build_reply_messages(
	jd_text: str,
	evaluation: dict[str, Any],
	conversation: str,
	intent: str,
) -> list[dict[str, str]]:
	identity = str(evaluation.get("candidate_name") or "").strip()
	safe_evaluation = json_clone(evaluation)
	if isinstance(safe_evaluation, dict):
		safe_evaluation.pop("candidate_name", None)
		_redact_reply_value(safe_evaluation, identity=identity)
	safe_conversation = redact_contact_text(conversation)
	if len(identity) >= 2:
		safe_conversation = safe_conversation.replace(identity, "[姓名已脱敏]")
	payload = {
		"job_description": redact_contact_text(jd_text),
		"evaluation": safe_evaluation,
		"conversation": safe_conversation[-6000:],
		"intent": intent,
		"output_schema": {
			"intent": "string",
			"reply": "string",
			"reason": "string",
			"requires_human_review": True,
			"prohibited_content_detected": "boolean",
		},
	}
	return [
		{
			"role": "system",
			"content": (
				"你是招聘沟通助手，只生成待人工审核的中文回复草稿。"
				"不得承诺录用、虚构薪资或面试安排，不得询问婚育、年龄、健康等无关隐私。"
				"只引用输入中已有事实；回复简洁、礼貌、具体。严格输出 JSON。"
			),
		},
		{"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
	]


def generate_reply_draft(
	service: ChatService,
	jd_text: str,
	evaluation: dict[str, Any],
	conversation: str,
	intent: str,
) -> dict[str, Any]:
	if intent == "auto":
		intent = recommended_reply_intent(evaluation)
	raw = service.chat(build_reply_messages(jd_text, evaluation, conversation, intent), temperature=0.3)
	result = parse_ai_json(raw)
	reply = result.get("reply")
	if not isinstance(reply, str) or not reply.strip():
		raise RecruiterAIError("AI 结果缺少非空 reply")
	result["intent"] = intent
	result["reply"] = reply.strip()
	result["requires_human_review"] = True
	result["prohibited_content_detected"] = bool(result.get("prohibited_content_detected", False))
	return result
