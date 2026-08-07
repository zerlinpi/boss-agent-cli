"""BOSS-backed recruiter AI screening commands."""

from __future__ import annotations

from typing import Any

import click

from boss_agent_cli.ai.service import AIServiceError
from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.compliance import require_compliance_allowed
from boss_agent_cli.commands._recruiter_platform import get_recruiter_platform_instance
from boss_agent_cli.commands.recruiter.ai_common import (
	AIConfigurationError,
	draft_for_records,
	emit_ai_error,
	emit_input_error,
	evaluate_local,
	platform_error,
	ranked_records_for_run,
	resolve_job,
	service_for,
)
from boss_agent_cli.commands.recruiter.resume_parser import parse_resume
from boss_agent_cli.display import handle_auth_errors, handle_output, handle_platform_error_output
from boss_agent_cli.recruiter_ai import (
	RecruiterAIError,
	RecruiterAIStore,
	candidate_items,
	conversation_to_text,
	extract_candidate_ref,
	summarize_ranking,
)


def _candidate_ref_key(ref: dict[str, Any]) -> str | None:
	for field in ("geek_id", "security_id", "friend_id"):
		value = ref.get(field)
		if value not in (None, ""):
			return f"{field}:{value}"
	return None


@click.command("evaluate-geek")
@click.argument("geek_id")
@click.option("--job-id", required=True, help="BOSS 职位 ID")
@click.option("--security-id", required=True, help="候选人安全 ID")
@click.option("--friend-id", default=None, help="聊天会话 friend ID")
@click.option("--job-key", required=True, help="岗位唯一标识")
@click.option("--jd", "jd_input", default=None, help="岗位 JD；省略时读取已保存岗位配置")
@click.option("--rubric", "rubric_input", default=None, help="评分规则 JSON")
@click.option("--force", is_flag=True, help="忽略未变化检测并重新评估")
@click.pass_context
@handle_auth_errors("recruiter-ai-evaluate-geek")
def evaluate_geek_cmd(
	ctx: click.Context,
	geek_id: str,
	job_id: str,
	security_id: str,
	friend_id: str | None,
	job_key: str,
	jd_input: str | None,
	rubric_input: str | None,
	force: bool,
) -> None:
	"""读取当前授权范围内的 BOSS 候选人简历并评估。"""
	if not require_compliance_allowed(ctx, "recruiter-resume"):
		return
	service = service_for(ctx, deferred=True)
	if service is None:
		return
	store = RecruiterAIStore(ctx.obj["data_dir"])
	try:
		jd_text, rubric = resolve_job(
			store, job_key=job_key, jd_input=jd_input, rubric_input=rubric_input,
		)
	except RecruiterAIError as exc:
		emit_input_error(ctx, str(exc))
		return
	auth = AuthManager(
		ctx.obj["data_dir"], logger=ctx.obj["logger"],
		platform=ctx.obj.get("platform", "zhipin"),
	)
	with get_recruiter_platform_instance(ctx, auth) as platform:
		result = platform.view_geek(geek_id, job_id, security_id=security_id)
		if not platform.is_success(result):
			handle_platform_error_output(
				ctx, "recruiter-ai-evaluate-geek", platform, result,
				fallback_message="候选人简历获取失败",
			)
			return
		try:
			record = evaluate_local(
				service=service, store=store, jd_text=jd_text, rubric=rubric,
				resume_payload=parse_resume(result), job_key=job_key,
				source={
					"type": "zhipin", "geek_id": geek_id, "job_id": job_id,
					"security_id": security_id, "friend_id": friend_id,
				},
				save=True, force=force,
			)
		except RecruiterAIError as exc:
			emit_input_error(ctx, str(exc))
			return
		except AIServiceError as exc:
			emit_ai_error(ctx, "recruiter-ai-evaluate-geek", exc)
			return
	handle_output(
		ctx, "recruiter-ai-evaluate-geek", record,
		hints={"next_actions": [f"boss hr ai report --job-key {job_key}"]},
	)


@click.command("screen-applications")
@click.option("--job-key", required=True, help="已保存岗位配置的唯一标识")
@click.option("--job-id", required=True, help="BOSS 职位 ID")
@click.option("--label-id", default=0, type=int, show_default=True, help="候选人列表标签")
@click.option("--pages", default=1, type=click.IntRange(1, 10), show_default=True)
@click.option("--limit", default=30, type=click.IntRange(1, 100), show_default=True)
@click.option("--top", default=20, type=click.IntRange(1, 100), show_default=True)
@click.option("--force", is_flag=True, help="重新评估未变化的候选人")
@click.option("--draft-top", default=0, type=click.IntRange(0, 20), help="为前 N 名生成回复草稿")
@click.option("--include-chat", is_flag=True, help="生成草稿时读取候选人聊天上下文")
@click.pass_context
@handle_auth_errors("recruiter-ai-screen-applications")
def screen_applications_cmd(
	ctx: click.Context,
	job_key: str,
	job_id: str,
	label_id: int,
	pages: int,
	limit: int,
	top: int,
	force: bool,
	draft_top: int,
	include_chat: bool,
) -> None:
	"""读取授权范围内的 BOSS 投递列表并完成筛选闭环，不自动发送消息。"""
	if not require_compliance_allowed(ctx, "recruiter-applications"):
		return
	if not require_compliance_allowed(ctx, "recruiter-resume"):
		return
	if include_chat and not require_compliance_allowed(ctx, "recruiter-chatmsg"):
		return
	service = service_for(ctx, deferred=True)
	if service is None:
		return
	store = RecruiterAIStore(ctx.obj["data_dir"])
	try:
		jd_text, rubric = resolve_job(store, job_key=job_key, jd_input=None, rubric_input=None)
	except RecruiterAIError as exc:
		emit_input_error(ctx, str(exc))
		return

	auth = AuthManager(
		ctx.obj["data_dir"], logger=ctx.obj["logger"],
		platform=ctx.obj.get("platform", "zhipin"),
	)
	processed: list[str] = []
	skipped: list[str] = []
	failed: list[dict[str, str]] = []
	refs: list[dict[str, Any]] = []
	seen_refs: set[str] = set()
	with get_recruiter_platform_instance(ctx, auth) as platform:
		for page in range(1, pages + 1):
			result = platform.friend_list(page=page, label_id=label_id, job_id=job_id)
			if not platform.is_success(result):
				handle_platform_error_output(
					ctx, "recruiter-ai-screen-applications", platform, result,
					fallback_message="候选人投递列表获取失败",
				)
				return
			for item in candidate_items(platform.unwrap_data(result) or {}):
				ref = extract_candidate_ref(item, default_job_id=job_id)
				key = _candidate_ref_key(ref)
				if key is not None and key in seen_refs:
					continue
				if key is not None:
					seen_refs.add(key)
				refs.append(ref)
				if len(refs) >= limit:
					break
			if len(refs) >= limit:
				break

		for ref in refs[:limit]:
			geek_id = str(ref.get("geek_id") or "")
			security_id = str(ref.get("security_id") or "")
			candidate_job_id = str(ref.get("job_id") or job_id)
			if not geek_id or not security_id:
				failed.append({
					"candidate": str(ref.get("name") or "candidate"),
					"error": "候选人列表缺少 geek_id 或 security_id，无法读取简历",
				})
				continue
			result = platform.view_geek(geek_id, candidate_job_id, security_id=security_id)
			if not platform.is_success(result):
				failed.append({
					"candidate": str(ref.get("name") or geek_id),
					"error": platform_error(platform, result, "候选人简历获取失败"),
				})
				continue
			try:
				record = evaluate_local(
					service=service, store=store, jd_text=jd_text, rubric=rubric,
					resume_payload=parse_resume(result), job_key=job_key,
					source={
						"type": "zhipin", "geek_id": geek_id,
						"security_id": security_id, "job_id": candidate_job_id,
						"friend_id": ref.get("friend_id"),
					},
					save=True, force=force,
				)
				(skipped if record.get("skipped") else processed).append(str(record.get("id", geek_id)))
			except AIConfigurationError as exc:
				emit_ai_error(ctx, "recruiter-ai-screen-applications", exc)
				return
			except (RecruiterAIError, AIServiceError) as exc:
				failed.append({"candidate": str(ref.get("name") or geek_id), "error": str(exc)})

		ranked_records, draft_records = ranked_records_for_run(
			store,
			job_key=job_key,
			top=top,
			draft_top=draft_top,
			processed_ids=processed,
		)
		drafts: list[dict[str, Any]] = []
		draft_failed: list[dict[str, str]] = []
		if draft_top and draft_records:
			try:
				drafts, draft_failed = draft_for_records(
					service=service, store=store, platform=platform,
					records=draft_records, limit=draft_top, include_chat=include_chat,
					conversation_parser=conversation_to_text,
				)
			except AIConfigurationError as exc:
				emit_ai_error(ctx, "recruiter-ai-screen-applications", exc)
				return

	handle_output(
		ctx, "recruiter-ai-screen-applications",
		{
			"job_key": job_key, "job_id": job_id,
			"discovered_count": len(refs),
			"processed_count": len(processed),
			"skipped_unchanged_count": len(skipped),
			"failed_count": len(failed),
			"evaluation_ids": processed, "skipped_ids": skipped, "failed": failed,
			"ranking": summarize_ranking(ranked_records[:top]),
			"reply_drafts": drafts, "reply_draft_failures": draft_failed,
			"messages_sent": 0, "human_review_required": True,
		},
		hints={"next_actions": [
			f"boss hr ai report --job-key {job_key} --top {top}",
			"人工审核 reply_drafts 后回到 BOSS 官方页面发送",
		]},
	)
