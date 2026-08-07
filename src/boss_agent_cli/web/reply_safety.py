"""Deterministic safety checks for AI-generated recruiter reply drafts."""

from __future__ import annotations

import re

_PROTECTED_ATTRIBUTE = re.compile(
	r"婚育|结婚|未婚|已婚|怀孕|备孕|生育|孩子|年龄|性别|民族|宗教|政治面貌|"
	r"健康状况|疾病|残疾|户籍性质",
	re.IGNORECASE,
)
_EMPLOYMENT_PROMISE = re.compile(r"保证录用|一定录用|确定录用|已经录用|直接录用|肯定录用")
_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d(?:[- ]?\d){8}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_WECHAT = re.compile(r"(?:微信|微信号|wechat|weixin)\s*[:：]?\s*[A-Za-z0-9_-]{5,}", re.IGNORECASE)


def scan_reply_safety(reply: str) -> list[str]:
	"""Return stable safety flags for a recruiter reply draft."""
	flags: list[str] = []
	if len(reply) > 1200:
		flags.append("reply_too_long")
	if _PROTECTED_ATTRIBUTE.search(reply):
		flags.append("protected_attribute")
	if _EMPLOYMENT_PROMISE.search(reply):
		flags.append("employment_promise")
	if _PHONE.search(reply) or _EMAIL.search(reply) or _WECHAT.search(reply):
		flags.append("contact_exposure")
	return flags
