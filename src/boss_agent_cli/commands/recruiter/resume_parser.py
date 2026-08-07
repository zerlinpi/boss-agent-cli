"""招聘者 — 简历数据结构化解析。

将 BOSS 直聘 view_geek 原始响应转为干净的 JSON 结构，
方便 Agent、CLI 和 Web 招聘工作台消费。
"""
from __future__ import annotations

from typing import Any


def _safe_str(val: Any) -> str:
	if val is None:
		return ""
	return str(val)


def _dict_list(value: Any) -> list[dict[str, Any]]:
	"""Normalize optional API list fields without trusting remote payload shape."""
	if not isinstance(value, list):
		return []
	return [item for item in value if isinstance(item, dict)]


def _gender_label(base: dict[str, Any]) -> str:
	"""Use an explicit label when available and never guess unknown gender codes."""
	description = base.get("genderDesc")
	if isinstance(description, str) and description.strip():
		return description.strip()
	value = base.get("gender")
	if value in (1, "1", "男", "male", "Male", "M", "m"):
		return "男"
	# Historical BOSS payloads used 0 for female in this parser's original contract.
	if value in (0, "0", "女", "female", "Female", "F", "f"):
		return "女"
	return ""


def _parse_base(info: dict[str, Any]) -> dict[str, Any]:
	base = info.get("geekBaseInfo", {})
	if not isinstance(base, dict):
		base = {}
	return {
		"name": base.get("name", ""),
		"gender": _gender_label(base),
		"age": base.get("ageDesc", ""),
		"degree": base.get("degreeCategory", ""),
		"work_years": base.get("workYearDesc", ""),
		"active_status": base.get("activeTimeDesc", ""),
		"avatar": base.get("large", ""),
	}


def _parse_expect(info: dict[str, Any]) -> dict[str, Any]:
	ex = info.get("showExpectPosition") or {}
	if not isinstance(ex, dict):
		ex = {}
	return {
		"position": ex.get("positionName", ""),
		"salary": ex.get("salaryDesc", ""),
		"city": ex.get("locationName", ""),
	}


def _parse_works(info: dict[str, Any]) -> list[dict[str, Any]]:
	result = []
	for w in _dict_list(info.get("geekWorkExpList")):
		emphasis = w.get("workEmphasis")
		result.append({
			"company": w.get("company", ""),
			"position": w.get("positionName", ""),
			"department": w.get("department", ""),
			"start": w.get("startYearMonStr", ""),
			"end": w.get("endYearMonStr", ""),
			"duration": w.get("workYearDesc", ""),
			"responsibility": w.get("responsibility", ""),
			"performance": w.get("workPerformance", ""),
			"keywords": emphasis.split("#&#") if isinstance(emphasis, str) and emphasis else [],
		})
	return result


def _parse_projects(info: dict[str, Any]) -> list[dict[str, Any]]:
	result = []
	for p in _dict_list(info.get("geekProjExpList")):
		result.append({
			"name": p.get("name", ""),
			"role": p.get("roleName", ""),
			"start": p.get("startDateDesc", ""),
			"end": p.get("endDateDesc", ""),
			"duration": p.get("workYearDesc", ""),
			"description": p.get("projectDescription", ""),
			"achievement": p.get("performance", ""),
		})
	return result


def _parse_education(info: dict[str, Any]) -> list[dict[str, Any]]:
	result = []
	for e in _dict_list(info.get("geekEduExpList")):
		result.append({
			"school": e.get("school", ""),
			"major": e.get("major", ""),
			"degree": e.get("degreeDesc", ""),
			"start": e.get("startYearMonStr", ""),
			"end": e.get("endYearMonStr", ""),
		})
	return result


def _parse_competitive(info: dict[str, Any]) -> list[str]:
	jc = info.get("jobCompetitive") or {}
	if not isinstance(jc, dict):
		return []
	return [
		str(t.get("content", ""))
		for t in _dict_list(jc.get("tips"))
		if t.get("content")
	]


def parse_resume(raw: dict[str, Any]) -> dict[str, Any]:
	"""从 view_geek 响应解析结构化简历。"""
	payload = raw.get("zpData") if "zpData" in raw else raw.get("data", raw)
	if not isinstance(payload, dict):
		payload = {}
	info = payload.get("geekDetailInfo", {})
	if not isinstance(info, dict):
		info = {}

	certs = [
		_safe_str(c.get("certName"))
		for c in _dict_list(info.get("geekCertificationList"))
		if c.get("certName")
	]

	return {
		"basic": _parse_base(info),
		"expectation": _parse_expect(info),
		"work_experience": _parse_works(info),
		"project_experience": _parse_projects(info),
		"education": _parse_education(info),
		"competitive_analysis": _parse_competitive(info),
		"certifications": certs,
	}
