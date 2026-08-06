"""招聘者 AI 辅助：简历评估、批量排序与回复草稿。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from boss_agent_cli.ai.config import AIConfigStore
from boss_agent_cli.ai.service import AIService, AIServiceError
from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.compliance import require_compliance_allowed
from boss_agent_cli.commands._recruiter_platform import get_recruiter_platform_instance
from boss_agent_cli.commands.recruiter.resume_parser import parse_resume
from boss_agent_cli.display import handle_auth_errors, handle_error_output, handle_output, handle_platform_error_output
from boss_agent_cli.recruiter_ai import (
	RecruiterAIError,
	RecruiterAIStore,
	evaluate_resume,
	generate_reply_draft,
	normalize_resume,
	read_json_input,
	read_text_input,
	summarize_ranking,
)


def _service(ctx: click.Context) -> AIService | None:
	store = AIConfigStore(ctx.obj["data_dir"])
	if not store.is_configured():
		handle_error_output(
			ctx,
			"recruiter-ai",
			code="AI_NOT_CONFIGURED",
			message="AI 服务未配置",
			recoverable=True,
			recovery_action="boss ai config --provider <provider> --model <model> --api-key <key>",
		)
		return None
	config = store.load_config()
	api_key = store.get_api_key()
	base_url = store.get_base_url()
	model = config.get("ai_model")
	if not api_key or not base_url or not isinstance(model, str):
		handle_error_output(
			ctx,
			"recruiter-ai",
			code="AI_NOT_CONFIGURED",
			message="AI 配置不完整",
			recoverable=True,
			recovery_action="boss ai config",
		)
		return None
	return AIService(
		base_url=base_url,
		api_key=api_key,
		model=model,
		temperature=float(config.get("ai_temperature", 0.2)),
		max_tokens=int(config.get("ai_max_tokens", 4096)),
	)


def _emit_input_error(ctx: click.Context, message: str) -> None:
	handle_error_output(
		ctx,
		"recruiter-ai",
		code="INVALID_PARAM",
		message=message,
		recoverable=False,
	)


def _evaluate_local(
	ctx: click.Context,
	*,
	service: AIService,
	store: RecruiterAIStore,
	jd_text: str,
	resume_payload: dict[str, Any],
	job_key: str,
	source: dict[str, Any],
	save: bool,
) -> dict[str, Any]:
	resume = normalize_resume(resume_payload)
	evaluation = evaluate_resume(service, jd_text, resume)
	if not save:
		return {
			"job_key": job_key,
			"resume": resume,
			"evaluation": evaluation,
			"source": source,
			"saved": False,
		}
	record = store.save_evaluation(
		job_key=job_key,
		jd_text=jd_text,
		resume=resume,
		evaluation=evaluation,
		source=source,
	)
	record["saved"] = True
	return record


@click.group("ai", help="招聘者 AI 简历评估、候选人排序和回复草稿")
def ai_group() -> None:
	"""招聘者 AI 工作台。"""


@ai_group.command("evaluate")
@click.option("--jd", "jd_input", required=True, help="岗位 JD 文本或 @文件路径")
@click.option("--resume", "resume_input", required=True, help="结构化简历 JSON 或 @文件路径")
@click.option("--job-key", required=True, help="岗位唯一标识，用于归档和排行榜")
@click.option("--save/--no-save", default=True, help="是否保存本地评估记录")
@click.pass_context
def evaluate_cmd(ctx: click.Context, jd_input: str, resume_input: str, job_key: str, save: bool) -> None:
	"""评估一份本地 JSON 简历。"""
	service = _service(ctx)
	if service is None:
		return
	try:
		jd_text = read_text_input(jd_input)
		resume_payload = read_json_input(resume_input)
		record = _evaluate_local(
			ctx,
			service=service,
			store=RecruiterAIStore(ctx.obj["data_dir"]),
			jd_text=jd_text,
			resume_payload=resume_payload,
			job_key=job_key,
			source={"type": "local", "input": resume_input if resume_input.startswith("@") else "inline"},
			save=save,
		)
	except RecruiterAIError as exc:
		_emit_input_error(ctx, str(exc))
		return
	except AIServiceError as exc:
		handle_error_output(
			ctx,
			"recruiter-ai-evaluate",
			code="AI_API_ERROR",
			message=f"AI 服务调用失败: {exc}",
			recoverable=True,
			recovery_action="检查 AI 配置和网络后重试",
		)
		return
	handle_output(
		ctx,
		"recruiter-ai-evaluate",
		record,
		hints={"next_actions": [
			f"boss hr ai rank --job-key {job_key}",
			"boss hr ai reply --evaluation-id <id> --conversation @chat.txt --intent ask_followup",
		]},
	)


@ai_group.command("evaluate-geek")
@click.argument("geek_id")
@click.option("--job-id", required=True, help="BOSS 职位 ID")
@click.option("--security-id", required=True, help="候选人安全 ID")
@click.option("--jd", "jd_input", required=True, help="岗位 JD 文本或 @文件路径")
@click.option("--job-key", required=True, help="岗位唯一标识，用于归档和排行榜")
@click.pass_context
@handle_auth_errors("recruiter-ai-evaluate-geek")
def evaluate_geek_cmd(
	ctx: click.Context,
	geek_id: str,
	job_id: str,
	security_id: str,
	jd_input: str,
	job_key: str,
) -> None:
	"""读取当前授权范围内的 BOSS 候选人简历并评估。

	该命令沿用 recruiter-resume 的合规门禁；默认 Assisted Mode 会阻断。
	"""
	if not require_compliance_allowed(ctx, "recruiter-resume"):
		return
	service = _service(ctx)
	if service is None:
		return
	try:
		jd_text = read_text_input(jd_input)
	except RecruiterAIError as exc:
		_emit_input_error(ctx, str(exc))
		return

	data_dir = ctx.obj["data_dir"]
	auth = AuthManager(data_dir, logger=ctx.obj["logger"], platform=ctx.obj.get("platform", "zhipin"))
	with get_recruiter_platform_instance(ctx, auth) as platform:
		result = platform.view_geek(geek_id, job_id, security_id=security_id)
		if not platform.is_success(result):
			handle_platform_error_output(
				ctx,
				"recruiter-ai-evaluate-geek",
				platform,
				result,
				fallback_message="候选人简历获取失败",
			)
			return
		try:
			record = _evaluate_local(
				ctx,
				service=service,
				store=RecruiterAIStore(data_dir),
				jd_text=jd_text,
				resume_payload=parse_resume(result),
				job_key=job_key,
				source={
					"type": "zhipin",
					"geek_id": geek_id,
					"job_id": job_id,
					"security_id": security_id,
				},
				save=True,
			)
		except RecruiterAIError as exc:
			_emit_input_error(ctx, str(exc))
			return
		except AIServiceError as exc:
			handle_error_output(
				ctx,
				"recruiter-ai-evaluate-geek",
				code="AI_API_ERROR",
				message=f"AI 服务调用失败: {exc}",
				recoverable=True,
				recovery_action="检查 AI 配置和网络后重试",
			)
			return

	handle_output(
		ctx,
		"recruiter-ai-evaluate-geek",
		record,
		hints={"next_actions": [f"boss hr ai rank --job-key {job_key}"]},
	)


@ai_group.command("batch")
@click.option("--jd", "jd_input", required=True, help="岗位 JD 文本或 @文件路径")
@click.option("--resume-dir", required=True, type=click.Path(path_type=Path), help="简历 JSON 目录")
@click.option("--pattern", default="*.json", show_default=True, help="文件匹配模式")
@click.option("--job-key", required=True, help="岗位唯一标识")
@click.option("--top", default=20, type=click.IntRange(1, 200), show_default=True, help="输出排行榜数量")
@click.option("--limit", default=50, type=click.IntRange(1, 500), show_default=True, help="本次最多评估的文件数")
@click.pass_context
def batch_cmd(
	ctx: click.Context,
	jd_input: str,
	resume_dir: Path,
	pattern: str,
	job_key: str,
	top: int,
	limit: int,
) -> None:
	"""批量评估目录中的 JSON 简历并输出排行榜。"""
	service = _service(ctx)
	if service is None:
		return
	try:
		jd_text = read_text_input(jd_input)
	except RecruiterAIError as exc:
		_emit_input_error(ctx, str(exc))
		return
	resume_dir = resume_dir.expanduser()
	if not resume_dir.is_dir():
		_emit_input_error(ctx, f"简历目录不存在: {resume_dir}")
		return

	store = RecruiterAIStore(ctx.obj["data_dir"])
	processed: list[str] = []
	failed: list[dict[str, str]] = []
	for path in sorted(resume_dir.glob(pattern))[:limit]:
		if not path.is_file():
			continue
		try:
			payload = read_json_input(f"@{path}")
			record = _evaluate_local(
				ctx,
				service=service,
				store=store,
				jd_text=jd_text,
				resume_payload=payload,
				job_key=job_key,
				source={"type": "batch", "path": str(path)},
				save=True,
			)
			processed.append(str(record.get("id", path.name)))
		except (RecruiterAIError, AIServiceError) as exc:
			failed.append({"file": str(path), "error": str(exc)})

	ranking = summarize_ranking(store.rank(job_key=job_key, top=top))
	handle_output(
		ctx,
		"recruiter-ai-batch",
		{
			"job_key": job_key,
			"processed_count": len(processed),
			"failed_count": len(failed),
			"evaluation_ids": processed,
			"failed": failed,
			"ranking": ranking,
		},
		hints={"next_actions": [
			f"boss hr ai rank --job-key {job_key} --top {top}",
		]},
	)


@ai_group.command("rank")
@click.option("--job-key", required=True, help="岗位唯一标识")
@click.option("--top", default=20, type=click.IntRange(1, 200), show_default=True)
@click.pass_context
def rank_cmd(ctx: click.Context, job_key: str, top: int) -> None:
	"""查看已保存候选人的本地排行榜。"""
	store = RecruiterAIStore(ctx.obj["data_dir"])
	ranking = summarize_ranking(store.rank(job_key=job_key, top=top))
	handle_output(
		ctx,
		"recruiter-ai-rank",
		{"job_key": job_key, "count": len(ranking), "ranking": ranking},
		hints={"next_actions": [
			"boss hr ai reply --evaluation-id <id> --conversation @chat.txt --intent ask_followup",
		]},
	)


@ai_group.command("reply")
@click.option("--evaluation-id", required=True, help="评估记录 ID")
@click.option("--conversation", required=True, help="聊天上下文文本或 @文件路径")
@click.option(
	"--intent",
	required=True,
	type=click.Choice(["acknowledge", "ask_followup", "invite_interview", "clarify", "decline_draft"]),
	help="回复目的",
)
@click.pass_context
def reply_cmd(ctx: click.Context, evaluation_id: str, conversation: str, intent: str) -> None:
	"""根据评估和聊天上下文生成待人工审核的回复草稿。"""
	service = _service(ctx)
	if service is None:
		return
	store = RecruiterAIStore(ctx.obj["data_dir"])
	try:
		record = store.get_evaluation(evaluation_id)
		conversation_text = read_text_input(conversation)
		evaluation = record.get("evaluation")
		jd_text = record.get("jd_text")
		if not isinstance(evaluation, dict) or not isinstance(jd_text, str):
			raise RecruiterAIError(f"评估记录缺少必要字段: {evaluation_id}")
		draft = generate_reply_draft(service, jd_text, evaluation, conversation_text, intent)
		reply_record = store.save_reply(
			evaluation_id=evaluation_id,
			intent=intent,
			conversation=conversation_text,
			draft=draft,
		)
	except RecruiterAIError as exc:
		_emit_input_error(ctx, str(exc))
		return
	except AIServiceError as exc:
		handle_error_output(
			ctx,
			"recruiter-ai-reply",
			code="AI_API_ERROR",
			message=f"AI 服务调用失败: {exc}",
			recoverable=True,
			recovery_action="检查 AI 配置和网络后重试",
		)
		return

	handle_output(
		ctx,
		"recruiter-ai-reply",
		reply_record,
		hints={"next_actions": ["人工检查 draft.reply 后，再回到 BOSS 官方页面发送"]},
	)
