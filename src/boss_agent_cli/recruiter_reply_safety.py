"""Deterministic safety checks for recruiter reply drafts."""

from __future__ import annotations

import re

_PROTECTED_ATTRIBUTE = re.compile(
	r"婚育|婚姻状况|结婚|未婚|已婚|怀孕|孕期|备孕|生育|育儿|孩子|家庭情况|"
	r"年龄|出生日期|生日|性别|民族|种族|国籍|宗教|政治面貌|政治身份|党派|党员|"
	r"健康状况|疾病|残疾|残障|户籍性质|户口|籍贯|"
	r"\bage\b|\bgender\b|marital\s*status|pregnan|fertility|disabilit|religion|"
	r"\brace\b|ethnicity|nationality|political\s*affiliation|health\s*status",
	re.IGNORECASE,
)
_EMPLOYMENT_PROMISE = re.compile(
	r"保证录用|一定录用|确定录用|已经录用|直接录用|肯定录用|你已被录用|你被录用|"
	r"录用已确定|(?:我们|公司)?\s*(?:决定|确认|正式)\s*(?:录用|录取)\s*(?:你|您)?|"
	r"恭喜[^。！？\n]{0,30}(?:被录用|被录取|录用通过|录取通过)|欢迎(?:你|您)?\s*入职|"
	r"(?:offer|Offer)\s*已(?:确认|确定)|直接发\s*(?:offer|Offer)|"
	r"guaranteed\s+(?:offer|employment)|definitely\s+hired",
	re.IGNORECASE,
)
_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d(?:[- ]?\d){8}(?!\d)")
_LANDLINE = re.compile(r"(?<!\d)0\d{2,3}[- ]?\d{7,8}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_WECHAT = re.compile(r"(?:微信|微信号|wechat|weixin)\s*[:：]?\s*[A-Za-z0-9_-]{5,}", re.IGNORECASE)
_QQ = re.compile(r"(?:QQ|qq)\s*[:：]?\s*[1-9]\d{4,11}")
_ID_NUMBER = re.compile(r"(?<!\d)(?:\d{17}[\dXx]|\d{15})(?!\d)")
_PASSPORT = re.compile(
	r"(?:护照号|护照号码|passport\s*(?:no\.?|number))\s*[:：#]?\s*[A-Z0-9]{5,20}",
	re.IGNORECASE,
)
_RESIDENTIAL_ADDRESS = re.compile(
	r"(?:家庭住址|家庭地址|现住址|现居住址|居住地址|住宅地址|详细住址|住址)"
	r"\s*[:：]\s*[^\n,，;；]{4,160}",
)


def scan_reply_safety(reply: str) -> list[str]:
	"""Return stable safety flags for a recruiter reply draft."""
	flags: list[str] = []
	if len(reply) > 1200:
		flags.append("reply_too_long")
	if _PROTECTED_ATTRIBUTE.search(reply):
		flags.append("protected_attribute")
	if _EMPLOYMENT_PROMISE.search(reply):
		flags.append("employment_promise")
	if any(pattern.search(reply) for pattern in (_ID_NUMBER, _PASSPORT, _RESIDENTIAL_ADDRESS)):
		flags.append("identity_exposure")
	if any(pattern.search(reply) for pattern in (_PHONE, _LANDLINE, _EMAIL, _WECHAT, _QQ)):
		flags.append("contact_exposure")
	return flags