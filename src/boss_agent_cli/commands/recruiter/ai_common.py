"""Shared helpers for recruiter AI CLI commands."""

from __future__ import annotations

from typing import Any

import click

from boss_agent_cli.ai.config import AIConfigStore
from boss_agent_cli.ai.service import AIService, AIServiceError
from boss_agent_cli.display import handle_error_output
from boss_agent_cli.recruiter_ai import (
	RecruiterAIError,
	RecruiterAIStore,
	evaluate_resume,
	generate_reply_draft,
	normalize_resume,
	normalize_rubric,
	read_json_input,
	read_text_input,
	recommended_reply_intent,
)


def service_for(ctx: click.Context) -> AIService | None:
	store = AIConfigStore(ctx.obj["data_dir"])
	if not store.is_configured():
		handle_error_output(
			ctx, "recruiter-ai", code="AI_NOT_CONFIGURED",
			message="AI 服务未配置", recoverable=True,
			recovery_action="boss ai config --provider <provider> --model <model> --api-key <key>",
		)
		return None
	config = store.load_config()
	api_key, base_url, model = store.get_api_key(), store.get_base_url(), config.get("ai_model")
	if not api_key or not base_url or not isinstance(model, str):
		handle_error_output(
			ctx, "recruiter-ai", code="AI_NOT_CONFIGURED",
			message="AI 配置不完整", recoverable=True,
			recovery_action="boss ai config",
		)
		return None
	return AIService(
		base_url=base_url, api_key=api_key, model=model,
		temperature=float(config.get("ai_temperature", 0.2)),
		max_tokens=int(config.get("ai_max_tokens", 4096)),
	)


def emit_input_error(ctx: click.Context, message: str) -> None:
	handle_error_output(
		ctx, "recruiter-ai", code="INVALID_PARAM",
		message=message, recoverable=False,
	)


def emit_ai_error(ctx: click.Context, command: str, exc: AIServiceError) -> None:
	handle_error_output(
		ctx, command, code="AI_API_ERROR",
		message=f"AI 服务调用失败: {exc}", recoverable=True,
		recovery_action="检查 AI 配置和网络后重试",
	)


def load_rubric(rubric_input: str | None) -> dict[str, Any]:
	return normalize_rubric(read_json_input(rubric_input)) if rubric_input else normalize_rubric()


def resolve_job(
	store: RecruiterAIStore,
	*,
	job_key: str,
	jd_input: str | None,
	rubric_input: str | None,
) -> tuple[str, dict[str, Any]]:
	if jd_input is not None:
		return read_text_input(jd_input), load_rubric(rubric_input)
	job = store.get_job(job_key)
	jd_text, rubric = job.get("jd_text"), job.get("rubric")
	if not isinstance(jd_text, str) or not jd_text.strip() or not isinstance(rubric, dict):
		raise RecruiterAIError(f"岗位配置缺少 JD 或评分规则: {job_key}")
	return jd_text, load_rubric(rubric_input) if rubric_input else normalize_rubric(rubric)


def evaluate_local(
	*,
	service: AIService,
	store: RecruiterAIStore,
	jd_text: str,
	rubric: dict[str, Any],
	resume_payload: dict[str, Any],
	job_key: str,
	source: dict[str, Any],
	save: bool,
	force: bool = False,
) -> dict[str, Any]:
	resume = normalize_resume(resume_payload)
	if save and not force:
		existing = store.find_unchanged(
			job_key=job_key, resume=resume, source=source, rubric=rubric,
		)
		if existing is not None:
			return {**existing, "saved": True, "skipped": True, "skip_reason": "unchanged"}
	evaluation = evaluate_resume(service, jd_text, resume, rubric)
	if not save:
		return {
			"job_key": job_key, "resume": resume, "evaluation": evaluation,
			"source": source, "saved": False, "skipped": False,
		}
	record = store.save_evaluation(
		job_key=job_key, jd_text=jd_text, resume=resume,
		evaluation=evaluation, source=source, rubric=rubric,
	)
	record.update({"saved": True, "skipped": False})
	return record


def platform_error(platform: Any, response: Any, fallback: str) -> str:
	try:
		code, message = platform.parse_error(response)
	except Exception:
		return fallback
	return f"{code}: {message or fallback}"


def draft_for_records(
	*,
	service: AIService,
	store: RecruiterAIStore,
	platform: Any | None,
	records: list[dict[str, Any]],
	limit: int,
	include_chat: bool,
	conversation_parser: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
	drafts: list[dict[str, Any]] = []
	failed: list[dict[str, str]] = []
	for record in records[:limit]:
		evaluation, jd_text, source = record.get("evaluation"), record.get("jd_text"), record.get("source")
		if not isinstance(evaluation, dict) or not isinstance(jd_text, str):
			continue
		conversation = ""
		if include_chat and platform is not None and isinstance(source, dict):
			friend_id = source.get("friend_id")
			if friend_id not in (None, ""):
				try:
					result = platform.chat_history(int(friend_id), count=30, max_msg_id=None)
					if platform.is_success(result):
						conversation = conversation_parser(platform.unwrap_data(result) or {})
					else:
						failed.append({
							"evaluation_id": str(record.get("id", "")),
							"error": platform_error(platform, result, "聊天记录获取失败"),
						})
				except (TypeError, ValueError, NotImplementedError) as exc:
					failed.append({"evaluation_id": str(record.get("id", "")), "error": str(exc)})
		try:
			intent = recommended_reply_intent(evaluation)
			draft = generate_reply_draft(service, jd_text, evaluation, conversation, intent)
			drafts.append(store.save_reply(
				evaluation_id=str(record.get("id", "")), intent=intent,
				conversation=conversation, draft=draft,
			))
		except (RecruiterAIError, AIServiceError) as exc:
			failed.append({"evaluation_id": str(record.get("id", "")), "error": str(exc)})
	return drafts, failed
