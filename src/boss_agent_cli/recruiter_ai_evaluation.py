"""Evidence-backed scoring and recruiter reply drafting."""

from __future__ import annotations

import json
from typing import Any

from boss_agent_cli.ai.service import AIService
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
				"score": "number between 0 and max_score",
				"max_score": "must equal rubric dimension max_score",
				"reason": "string",
				"evidence": ["concise resume facts"],
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
				"信息不足必须标记 unclear，不得推断。每个维度都必须提供证据。"
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
	"""Normalize model output and recompute scores using the configured rubric."""
	normalized_rubric = normalize_rubric(rubric)
	dimension_specs = {item["name"]: item for item in normalized_rubric["dimensions"]}
	raw_dimensions = payload.get("dimensions")
	if not isinstance(raw_dimensions, list):
		raise RecruiterAIError("AI 结果缺少 dimensions 列表")
	raw_by_name = {
		str(item.get("name")): item
		for item in raw_dimensions
		if isinstance(item, dict) and item.get("name") is not None
	}
	dimensions: list[dict[str, Any]] = []
	total_points = 0.0
	max_points = 0.0
	for name, spec in dimension_specs.items():
		item = raw_by_name.get(name, {})
		raw_score = item.get("score", 0) if isinstance(item, dict) else 0
		if not isinstance(raw_score, (int, float)) or isinstance(raw_score, bool):
			raw_score = 0
		max_score = float(spec["max_score"])
		score = max(0.0, min(max_score, float(raw_score)))
		total_points += score
		max_points += max_score
		dimensions.append({
			"name": name, "score": round(score, 2), "max_score": int(max_score),
			"reason": str(item.get("reason", "")).strip() if isinstance(item, dict) else "",
			"evidence": _as_text_list(item.get("evidence", []) if isinstance(item, dict) else []),
		})
	if max_points <= 0:
		raise RecruiterAIError("评分规则总分必须大于 0")
	total_score = int(round(total_points / max_points * 100))

	hard_results: list[dict[str, Any]] = []
	for item in payload.get("hard_requirements", []):
		if not isinstance(item, dict):
			continue
		status = str(item.get("status", "unclear")).lower()
		if status not in {"met", "missing", "unclear"}:
			status = "unclear"
		hard_results.append({
			"requirement": str(item.get("requirement", "")).strip(),
			"status": status, "evidence": _as_text_list(item.get("evidence", [])),
		})
	configured_hard = normalized_rubric["hard_requirements"]
	by_requirement = {item["requirement"]: item for item in hard_results if item["requirement"]}
	for spec in configured_hard:
		if spec["requirement"] not in by_requirement:
			hard_results.append({"requirement": spec["requirement"], "status": "unclear", "evidence": []})
	required_names = {item["requirement"] for item in configured_hard if item.get("required", True)}
	hard_missing = any(item["status"] == "missing" and item["requirement"] in required_names for item in hard_results)
	hard_unclear = any(item["status"] == "unclear" and item["requirement"] in required_names for item in hard_results)

	confidence = payload.get("confidence", 0.5)
	if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
		confidence = 0.5
	confidence = round(max(0.0, min(1.0, float(confidence))), 3)
	return {
		"total_score": total_score,
		"recommendation": _recommendation_for(
			total_score, normalized_rubric["thresholds"],
			hard_missing=hard_missing, hard_unclear=hard_unclear,
		),
		"confidence": confidence,
		"hard_requirements": hard_results,
		"dimensions": dimensions,
		"strengths": _as_text_list(payload.get("strengths", [])),
		"concerns": _as_text_list(payload.get("concerns", [])),
		"next_questions": _as_text_list(
			payload.get("next_questions", []), limit=normalized_rubric["max_questions"]
		),
		"summary": str(payload.get("summary", "")).strip(),
		"human_review_required": True,
		"score_source": "dimension_sum",
	}


def evaluate_resume(
	service: AIService,
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
			"intent": "string", "reply": "string", "reason": "string",
			"requires_human_review": True, "prohibited_content_detected": "boolean",
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
	service: AIService,
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
