"""Recruiter-side AI evaluation primitives.

The module is intentionally local-first: it consumes JD text and resume JSON that
is already available to the recruiter, strips protected attributes, asks an
OpenAI-compatible model for evidence-backed scoring, and persists auditable
records under the configured data directory.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, cast
from uuid import uuid4

from boss_agent_cli.ai.service import AIService
from boss_agent_cli.commands.recruiter.resume_parser import parse_resume

PROTECTED_BASIC_FIELDS = {
	"age",
	"avatar",
	"birth_date",
	"gender",
	"marital_status",
	"photo",
}

CONTACT_FIELDS = {
	"email",
	"mobile",
	"phone",
	"wechat",
	"weixin",
}

RECOMMENDATIONS = {
	"strong_interview",
	"interview",
	"manual_review",
	"not_recommended",
}

DEFAULT_DIMENSIONS: tuple[tuple[str, int], ...] = (
	("required_skills", 30),
	("relevant_experience", 20),
	("project_evidence", 15),
	("responsibility_match", 15),
	("industry_match", 10),
	("achievement_evidence", 10),
)


class RecruiterAIError(ValueError):
	"""Raised when recruiter AI input or output is invalid."""


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
	text = read_text_input(value)
	try:
		payload = json.loads(text)
	except json.JSONDecodeError as exc:
		raise RecruiterAIError(f"JSON 解析失败: {exc.msg}") from exc
	if not isinstance(payload, dict):
		raise RecruiterAIError("简历 JSON 顶层必须是对象")
	return cast("dict[str, Any]", payload)


def parse_ai_json(raw: str) -> dict[str, Any]:
	"""Parse a model response, tolerating fenced JSON."""
	text = raw.strip()
	if text.startswith("```"):
		text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
		text = re.sub(r"\s*```$", "", text)
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
	for key in ("data", "zpData"):
		value = payload.get(key)
		if isinstance(value, dict) and "geekDetailInfo" in value:
			return True
	return False


def normalize_resume(payload: dict[str, Any]) -> dict[str, Any]:
	"""Unwrap CLI envelopes, parse raw BOSS payloads, and remove protected data."""
	data: dict[str, Any] = payload
	if payload.get("ok") is True and isinstance(payload.get("data"), dict):
		data = cast("dict[str, Any]", payload["data"])

	if _looks_like_raw_boss_resume(data):
		data = parse_resume(data)
	else:
		data = json.loads(json.dumps(data, ensure_ascii=False))

	basic = data.get("basic")
	if isinstance(basic, dict):
		for field in PROTECTED_BASIC_FIELDS | CONTACT_FIELDS:
			basic.pop(field, None)

	for field in PROTECTED_BASIC_FIELDS | CONTACT_FIELDS:
		data.pop(field, None)
	return data


def redact_resume_for_model(resume: dict[str, Any]) -> dict[str, Any]:
	"""Create a model payload without identity or contact fields."""
	redacted = json.loads(json.dumps(resume, ensure_ascii=False))
	basic = redacted.get("basic")
	if isinstance(basic, dict):
		basic["name"] = "candidate"
	for field in CONTACT_FIELDS | {"name"}:
		redacted.pop(field, None)
	return cast("dict[str, Any]", redacted)


def redact_contact_text(text: str) -> str:
	"""Redact common phone numbers and email addresses before model calls."""
	text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号已脱敏]", text)
	return re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[邮箱已脱敏]", text)


def candidate_name(resume: dict[str, Any], *, fallback: str = "candidate") -> str:
	"""Extract a display name from a normalized resume."""
	basic = resume.get("basic")
	if isinstance(basic, dict):
		name = basic.get("name")
		if isinstance(name, str) and name.strip():
			return name.strip()
	name = resume.get("name")
	if isinstance(name, str) and name.strip():
		return name.strip()
	return fallback


def build_evaluation_messages(jd_text: str, resume: dict[str, Any]) -> list[dict[str, str]]:
	"""Build an evidence-backed and bias-reduced evaluation request."""
	dimensions = [{"name": name, "max_score": max_score} for name, max_score in DEFAULT_DIMENSIONS]
	payload = {
		"job_description": jd_text,
		"resume": redact_resume_for_model(resume),
		"scoring_dimensions": dimensions,
		"output_schema": {
			"candidate_name": "string",
			"total_score": "integer 0-100",
			"recommendation": "strong_interview|interview|manual_review|not_recommended",
			"confidence": "number 0-1",
			"hard_requirements": [
				{"requirement": "string", "status": "met|missing|unclear", "evidence": ["string"]}
			],
			"dimensions": [
				{
					"name": "one of scoring_dimensions.name",
					"score": "integer",
					"max_score": "integer",
					"reason": "string",
					"evidence": ["verbatim or concise resume facts"],
				}
			],
			"strengths": ["string"],
			"concerns": ["string"],
			"next_questions": ["string"],
			"summary": "string",
		},
	}
	return [
		{
			"role": "system",
			"content": (
				"你是招聘筛选助手。仅依据岗位相关能力和简历中的可验证证据评分。"
				"不得依据性别、年龄、照片、婚育、民族等受保护属性做判断；"
				"信息不足必须标记 unclear，不得推断。AI 只提供辅助建议，不作最终录用或淘汰决定。"
				"严格输出一个 JSON 对象，不要输出 Markdown。"
			),
		},
		{
			"role": "user",
			"content": json.dumps(payload, ensure_ascii=False),
		},
	]


def validate_evaluation(payload: dict[str, Any]) -> dict[str, Any]:
	"""Validate the minimum contract required by ranking and reply generation."""
	score = payload.get("total_score")
	if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= float(score) <= 100:
		raise RecruiterAIError("AI 结果 total_score 必须在 0-100 之间")
	recommendation = payload.get("recommendation")
	if recommendation not in RECOMMENDATIONS:
		raise RecruiterAIError("AI 结果 recommendation 不在允许范围内")
	confidence = payload.get("confidence")
	if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= float(confidence) <= 1:
		raise RecruiterAIError("AI 结果 confidence 必须在 0-1 之间")
	if not isinstance(payload.get("dimensions"), list):
		raise RecruiterAIError("AI 结果缺少 dimensions 列表")
	return payload


def evaluate_resume(service: AIService, jd_text: str, resume: dict[str, Any]) -> dict[str, Any]:
	"""Evaluate one normalized resume with the configured AI service."""
	raw = service.chat(build_evaluation_messages(jd_text, resume), temperature=0.1)
	result = validate_evaluation(parse_ai_json(raw))
	result["candidate_name"] = candidate_name(resume)
	result["human_review_required"] = True
	return result


def build_reply_messages(
	jd_text: str,
	evaluation: dict[str, Any],
	conversation: str,
	intent: str,
) -> list[dict[str, str]]:
	"""Build a concise recruiter reply-draft request."""
	payload = {
		"job_description": jd_text,
		"evaluation": evaluation,
		"conversation": redact_contact_text(conversation),
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
				"回复要简洁、礼貌、具体。严格输出 JSON，不要输出 Markdown。"
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
	"""Generate a reply draft; sending is deliberately outside this module."""
	raw = service.chat(build_reply_messages(jd_text, evaluation, conversation, intent), temperature=0.3)
	result = parse_ai_json(raw)
	reply = result.get("reply")
	if not isinstance(reply, str) or not reply.strip():
		raise RecruiterAIError("AI 结果缺少非空 reply")
	result["requires_human_review"] = True
	return result


class RecruiterAIStore:
	"""Persist evaluation and reply records as auditable local JSON files."""

	def __init__(self, data_dir: Path):
		self.root = data_dir / "recruiter-ai"
		self.evaluations_dir = self.root / "evaluations"
		self.replies_dir = self.root / "replies"
		self.evaluations_dir.mkdir(parents=True, exist_ok=True)
		self.replies_dir.mkdir(parents=True, exist_ok=True)

	@staticmethod
	def _new_id(prefix: str) -> str:
		stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
		return f"{prefix}_{stamp}_{uuid4().hex[:8]}"

	@staticmethod
	def _write(path: Path, payload: dict[str, Any]) -> None:
		path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

	def save_evaluation(
		self,
		*,
		job_key: str,
		jd_text: str,
		resume: dict[str, Any],
		evaluation: dict[str, Any],
		source: dict[str, Any] | None = None,
	) -> dict[str, Any]:
		record_id = self._new_id("eval")
		record = {
			"id": record_id,
			"created_at": datetime.now(timezone.utc).isoformat(),
			"job_key": job_key,
			"candidate_name": candidate_name(resume),
			"jd_text": jd_text,
			"resume": resume,
			"evaluation": evaluation,
			"source": source or {"type": "local"},
		}
		self._write(self.evaluations_dir / f"{record_id}.json", record)
		return record

	def get_evaluation(self, record_id: str) -> dict[str, Any]:
		path = self.evaluations_dir / f"{record_id}.json"
		if not path.is_file():
			raise RecruiterAIError(f"评估记录不存在: {record_id}")
		payload = json.loads(path.read_text(encoding="utf-8"))
		if not isinstance(payload, dict):
			raise RecruiterAIError(f"评估记录损坏: {record_id}")
		return cast("dict[str, Any]", payload)

	def list_evaluations(self, *, job_key: str | None = None) -> list[dict[str, Any]]:
		records: list[dict[str, Any]] = []
		for path in self.evaluations_dir.glob("eval_*.json"):
			try:
				payload = json.loads(path.read_text(encoding="utf-8"))
			except (OSError, json.JSONDecodeError):
				continue
			if not isinstance(payload, dict):
				continue
			if job_key is not None and payload.get("job_key") != job_key:
				continue
			records.append(cast("dict[str, Any]", payload))
		return records

	def rank(self, *, job_key: str, top: int) -> list[dict[str, Any]]:
		def score(record: dict[str, Any]) -> float:
			evaluation = record.get("evaluation")
			if not isinstance(evaluation, dict):
				return -1.0
			value = evaluation.get("total_score")
			return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else -1.0

		records = sorted(self.list_evaluations(job_key=job_key), key=score, reverse=True)
		return records[:top]

	def save_reply(
		self,
		*,
		evaluation_id: str,
		intent: str,
		conversation: str,
		draft: dict[str, Any],
	) -> dict[str, Any]:
		record_id = self._new_id("reply")
		record = {
			"id": record_id,
			"created_at": datetime.now(timezone.utc).isoformat(),
			"evaluation_id": evaluation_id,
			"intent": intent,
			"conversation": conversation,
			"draft": draft,
			"sent": False,
		}
		self._write(self.replies_dir / f"{record_id}.json", record)
		return record


def summarize_ranking(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Return a compact ranking payload for CLI and Agent consumption."""
	items: list[dict[str, Any]] = []
	for index, record in enumerate(records, 1):
		evaluation = record.get("evaluation")
		if not isinstance(evaluation, dict):
			continue
		items.append({
			"rank": index,
			"evaluation_id": record.get("id", ""),
			"candidate_name": record.get("candidate_name", ""),
			"total_score": evaluation.get("total_score"),
			"recommendation": evaluation.get("recommendation"),
			"confidence": evaluation.get("confidence"),
			"strengths": evaluation.get("strengths", []),
			"concerns": evaluation.get("concerns", []),
			"summary": evaluation.get("summary", ""),
		})
	return items
