"""Safety validation for local-AI generated recruiter reply drafts."""

from __future__ import annotations

import math
import re
from typing import Any, Callable

from boss_agent_cli.automation import reply_ai as reply_module

_INSTALLED = False
_MAX_REPLY_CHARS = 2000
_MAX_REASON_CHARS = 2000
_MAX_RISK_FLAGS = 20
_MAX_RISK_FLAG_CHARS = 128
_OUTBOUND_REVIEW_PATTERN = re.compile(
	r"年龄|出生日期|生日|性别|男生|女生|婚姻|婚育|怀孕|孕期|生育|家庭情况|"
	r"民族|种族|国籍|宗教|政治面貌|党员|党派|残疾|残障|健康状况|病史|疾病|"
	r"性取向|身高|体重|颜值|相貌|照片|身份证|押金|收费|付费|转账|保证金|"
	r"\bage\b|\bgender\b|\brace\b|ethnicity|religion|pregnan\w*|marital|"
	r"disabilit\w*|medical\s*(?:history|condition)|sexual\s*orientation",
	re.IGNORECASE,
)


def install_reply_draft_safety() -> None:
	"""Patch reply parsing so unsafe model output always falls back to human review."""
	global _INSTALLED
	if _INSTALLED:
		return
	_INSTALLED = True
	original: Callable[[str], Any] = reply_module.parse_reply_draft

	def parse_reply_draft(raw: str) -> Any:
		try:
			draft = original(raw)
		except ValueError as exc:
			# _draft_with_local_ai already treats TypeError as a safe parse failure.
			raise TypeError("reply draft contains invalid scalar values") from exc

		confidence = draft.confidence
		if not math.isfinite(confidence) or not 0 <= confidence <= 1:
			raise TypeError("reply draft confidence must be a finite number between 0 and 1")
		if len(draft.reply) > _MAX_REPLY_CHARS:
			raise TypeError(f"reply draft exceeds {_MAX_REPLY_CHARS} characters")
		if len(draft.reason) > _MAX_REASON_CHARS:
			raise TypeError(f"reply draft reason exceeds {_MAX_REASON_CHARS} characters")
		if len(draft.risk_flags) > _MAX_RISK_FLAGS:
			raise TypeError("reply draft contains too many risk flags")
		if any(len(flag) > _MAX_RISK_FLAG_CHARS for flag in draft.risk_flags):
			raise TypeError("reply draft risk flag is too long")

		risk_flags = list(draft.risk_flags)
		if draft.reply and _OUTBOUND_REVIEW_PATTERN.search(draft.reply):
			risk_flags.append("sensitive-outbound-content")
		if not draft.reply.strip():
			risk_flags.append("empty-outbound-content")
		if tuple(risk_flags) == draft.risk_flags:
			return draft
		return reply_module.ReplyDraft(
			action=draft.action,
			confidence=draft.confidence,
			reply=draft.reply,
			reason=draft.reason,
			risk_flags=tuple(dict.fromkeys(risk_flags)),
		)

	reply_module.parse_reply_draft = parse_reply_draft
