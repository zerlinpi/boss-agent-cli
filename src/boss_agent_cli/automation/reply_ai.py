"""Local-AI reply drafting for recruiter automation."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, replace
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from boss_agent_cli.ai.config import AIConfigStore
from boss_agent_cli.ai.local_models import RUNTIME_BASE_URLS
from boss_agent_cli.ai.service import AIService, AIServiceError
from boss_agent_cli.automation.config import AutomationConfig, ReplyStrategy
from boss_agent_cli.automation.models import Conversation, Decision, PlatformAction

_LOCAL_AI_PROVIDERS = frozenset(RUNTIME_BASE_URLS)
_MAX_REPLY_CHARS = 2000
_MAX_REASON_CHARS = 2000
_MAX_RISK_FLAGS = 20
_MAX_RISK_FLAG_CHARS = 128
_OUTBOUND_REVIEW_PATTERN = re.compile(
	r"年龄|出生日期|生日|性别|男生|女生|婚姻|婚育|怀孕|孕期|生育|家庭情况|"
	r"民族|种族|国籍|宗教|政治面貌|党员|党派|残疾|残障|健康状况|病史|疾病|"
	r"性取向|身高|体重|颜值|相貌|照片|身份证|押金|收费|付费|转账|保证金|"
	r"\bage\b|\bgender\b|\brace\b|ethnicity|nationality|religion|pregnan\w*|"
	r"marital|disabilit\w*|medical\s*(?:history|condition)|sexual\s*orientation",
	re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ReplyDraft:
	action: str
	confidence: float
	reply: str
	reason: str
	risk_flags: tuple[str, ...]


def apply_reply_strategy(
	decision: Decision,
	conversation: Conversation,
	config: AutomationConfig,
	data_dir: Path,
) -> Decision:
	"""Apply local-AI reply drafting while preserving the rule-chosen action."""
	if not _can_draft(decision):
		return decision
	match config.reply_strategy:
		case ReplyStrategy.TEMPLATE:
			return decision
		case ReplyStrategy.HYBRID | ReplyStrategy.LOCAL_AI:
			return _draft_with_local_ai(decision, conversation, config, data_dir)
		case unreachable:
			return unreachable


def _can_draft(decision: Decision) -> bool:
	return bool(
		decision.message
		and decision.action in {PlatformAction.SEND_QUESTIONNAIRE, PlatformAction.SEND_FOLLOW_UP}
	)


def _draft_with_local_ai(
	decision: Decision,
	conversation: Conversation,
	config: AutomationConfig,
	data_dir: Path,
) -> Decision:
	store = AIConfigStore(data_dir)
	ai_config = store.load_config()
	provider = str(ai_config.get("ai_provider", ""))
	if provider not in _LOCAL_AI_PROVIDERS:
		return decision
	api_key = store.get_api_key()
	base_url = store.get_base_url()
	model = ai_config.get("ai_model")
	if not api_key or not base_url or not model:
		return decision
	service = AIService(
		base_url=base_url,
		api_key=api_key,
		model=str(model),
		temperature=0.3,
		max_tokens=512,
	)
	try:
		raw = service.chat(_reply_messages(decision, conversation))
	except AIServiceError:
		return replace(decision, reason=f"{decision.reason}; local ai unavailable, template fallback")
	try:
		draft = parse_reply_draft(raw)
	except (JSONDecodeError, KeyError, TypeError):
		return replace(
			decision,
			confidence=min(decision.confidence, 0.5),
			requires_human=True,
			reason=f"{decision.reason}; local ai parse failed",
			risk_flags=(*decision.risk_flags, "local-ai-parse-error"),
		)
	if draft.action != decision.action.value:
		return replace(
			decision,
			requires_human=True,
			reason=f"{decision.reason}; local ai action mismatch: {draft.action}",
			risk_flags=(*decision.risk_flags, "local-ai-action-mismatch"),
		)
	if draft.confidence < config.human_review_threshold or draft.risk_flags:
		return replace(
			decision,
			message=draft.reply or decision.message,
			confidence=min(decision.confidence, draft.confidence),
			requires_human=True,
			reason=f"{decision.reason}; local ai review: {draft.reason}",
			risk_flags=(*decision.risk_flags, *draft.risk_flags),
		)
	return replace(
		decision,
		message=draft.reply,
		confidence=min(decision.confidence, draft.confidence),
		reason=f"{decision.reason}; local ai reply: {draft.reason}",
	)


def parse_reply_draft(raw: str) -> ReplyDraft:
	"""Parse and validate the strict JSON object produced by a local model."""
	text = raw.strip()
	if text.startswith("```"):
		text = "\n".join(line for line in text.splitlines() if not line.startswith("```")).strip()
	data = json.loads(text)
	if not isinstance(data, dict):
		raise TypeError("reply draft must be a JSON object")

	risk_flags_raw = data.get("risk_flags", [])
	if not isinstance(risk_flags_raw, list):
		raise TypeError("risk_flags must be a list")
	try:
		confidence = float(data["confidence"])
	except (TypeError, ValueError) as exc:
		raise TypeError("reply draft confidence must be numeric") from exc
	if not math.isfinite(confidence) or not 0 <= confidence <= 1:
		raise TypeError("reply draft confidence must be a finite number between 0 and 1")

	action = str(data["action"])
	reply = str(data["reply"])
	reason = str(data["reason"])
	risk_flags = tuple(str(item) for item in risk_flags_raw)
	if len(reply) > _MAX_REPLY_CHARS:
		raise TypeError(f"reply draft exceeds {_MAX_REPLY_CHARS} characters")
	if len(reason) > _MAX_REASON_CHARS:
		raise TypeError(f"reply draft reason exceeds {_MAX_REASON_CHARS} characters")
	if len(risk_flags) > _MAX_RISK_FLAGS:
		raise TypeError("reply draft contains too many risk flags")
	if any(len(flag) > _MAX_RISK_FLAG_CHARS for flag in risk_flags):
		raise TypeError("reply draft risk flag is too long")

	additional_risks: list[str] = []
	if not reply.strip():
		additional_risks.append("empty-outbound-content")
	if reply and _OUTBOUND_REVIEW_PATTERN.search(reply):
		additional_risks.append("sensitive-outbound-content")
	return ReplyDraft(
		action=action,
		confidence=confidence,
		reply=reply,
		reason=reason,
		risk_flags=tuple(dict.fromkeys((*risk_flags, *additional_risks))),
	)


def _reply_messages(decision: Decision, conversation: Conversation) -> list[dict[str, Any]]:
	transcript = "\n".join(conversation.all_messages or conversation.incoming_messages or conversation.outgoing_messages)
	payload = {
		"chosen_action": decision.action.value,
		"template_reply": decision.message,
		"conversation_title": conversation.title,
		"item_title": conversation.item_title,
		"transcript": transcript[-3000:],
		"output_schema": {
			"action": decision.action.value,
			"confidence": 0.0,
			"reply": "string",
			"reason": "string",
			"risk_flags": ["string"],
		},
	}
	return [
		{
			"role": "system",
			"content": (
				"你是招聘者自动回复文案助手。规则系统已经决定动作，"
				"你只能润色 reply，不能改变 action。只返回 JSON。"
			),
		},
		{"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
	]
