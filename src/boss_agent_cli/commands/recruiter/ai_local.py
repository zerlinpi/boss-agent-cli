"""Local-file and reporting commands for recruiter AI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from boss_agent_cli.ai.service import AIServiceError
from boss_agent_cli.commands.recruiter.ai_common import (
	draft_for_records,
	emit_ai_error,
	emit_input_error,
	evaluate_local,
	load_rubric,
	resolve_job,
	service_for,
)
from boss_agent_cli.display import handle_output
from boss_agent_cli.recruiter_ai import (
	CANDIDATE_STATUSES,
	RecruiterAIError,
	RecruiterAIStore,
	conversation_to_text,
	generate_reply_draft,
	normalize_rubric,
	read_json_input,
	read_text_input,
	recommended_reply_intent,
	summarize_ranking,
)


@click.command("configure")
@click.option("--job-key", required=True, help="岗位唯一标识")
@click.option("--jd", "jd_input", required=True, help="岗位 JD 文本或 @文件路径")
@click.option("--rubric", "rubric_input", default=None, help="评分规则 JSON 或 @文件路径")
@click.option("--boss-job-id", default=None, help="关联的 BOSS 职位 ID")
@click.pass_context
def configure_cmd(
	ctx: click.Context,
	job_key: str,
	jd_input: str,
	rubric_input: str | None,
	boss_job_id: str | None,
) -> None:
	"""保存岗位 JD 和评分规则，供后续一键筛选复用。"""
	try:
		record = RecruiterAIStore(ctx.obj["data_dir"]).save_job(
			job_key=job_key,
			jd_text=read_text_input(jd_input),
			rubric=load_rubric(rubric_input),
			metadata={"boss_job_id": boss_job_id} if boss_job_id else {},
		)
	except RecruiterAIError as exc:
		emit_input_error(ctx, str(exc))
		return
	handle_output(
		ctx, "recruiter-ai-configure", record,
		hints={"next_actions": [
			f"boss hr ai screen --job-key {job_key} --resume-dir ./resumes",
			f"boss hr ai screen-applications --job-key {job_key} --job-id <boss_job_id>",
		]},
	)


@click.command("jobs")
@click.pass_context
def jobs_cmd(ctx: click.Context) -> None:
	"""列出本地岗位筛选配置。"""
	jobs = RecruiterAIStore(ctx.obj["data_dir"]).list_jobs()
	handle_output(ctx, "recruiter-ai-jobs", {"count": len(jobs), "jobs": jobs})


@click.command("evaluate")
@click.option("--job-key", required=True, help="岗位唯一标识")
@click.option("--resume", "resume_input", required=True, help="结构化简历 JSON 或 @文件路径")
@click.option("--jd", "jd_input", default=None, help="岗位 JD；省略时读取已保存岗位配置")
@click.option("--rubric", "rubric_input", default=None, help="评分规则 JSON")
@click.option("--save/--no-save", default=True, help="是否保存本地评估记录")
@click.option("--force", is_flag=True, help="忽略未变化检测并重新评估")
@click.pass_context
def evaluate_cmd(
	ctx: click.Context,
	job_key: str,
	resume_input: str,
	jd_input: str | None,
	rubric_input: str | None,
	save: bool,
	force: bool,
) -> None:
	"""评估一份本地 JSON 简历。"""
	service = service_for(ctx)
	if service is None:
		return
	store = RecruiterAIStore(ctx.obj["data_dir"])
	try:
		jd_text, rubric = resolve_job(
			store, job_key=job_key, jd_input=jd_input, rubric_input=rubric_input,
		)
		record = evaluate_local(
			service=service, store=store, jd_text=jd_text, rubric=rubric,
			resume_payload=read_json_input(resume_input), job_key=job_key,
			source={"type": "local", "input": resume_input if resume_input.startswith("@") else "inline"},
			save=save, force=force,
		)
	except RecruiterAIError as exc:
		emit_input_error(ctx, str(exc))
		return
	except AIServiceError as exc:
		emit_ai_error(ctx, "recruiter-ai-evaluate", exc)
		return
	handle_output(
		ctx, "recruiter-ai-evaluate", record,
		hints={"next_actions": [
			f"boss hr ai report --job-key {job_key}",
			"boss hr ai reply --evaluation-id <id> --intent auto",
		]},
	)


@click.command("screen")
@click.option("--job-key", required=True, help="已保存岗位配置的唯一标识")
@click.option("--resume-dir", required=True, type=click.Path(path_type=Path), help="简历 JSON 目录")
@click.option("--pattern", default="*.json", show_default=True, help="文件匹配模式")
@click.option("--limit", default=100, type=click.IntRange(1, 500), show_default=True)
@click.option("--top", default=20, type=click.IntRange(1, 200), show_default=True)
@click.option("--force", is_flag=True, help="重新评估未变化的简历")
@click.option("--draft-top", default=0, type=click.IntRange(0, 50), help="为前 N 名生成回复草稿")
@click.pass_context
def screen_cmd(
	ctx: click.Context,
	job_key: str,
	resume_dir: Path,
	pattern: str,
	limit: int,
	top: int,
	force: bool,
	draft_top: int,
) -> None:
	"""一键批量筛选本地 JSON 简历、去重并生成排行榜。"""
	service = service_for(ctx)
	if service is None:
		return
	store = RecruiterAIStore(ctx.obj["data_dir"])
	try:
		jd_text, rubric = resolve_job(store, job_key=job_key, jd_input=None, rubric_input=None)
	except RecruiterAIError as exc:
		emit_input_error(ctx, str(exc))
		return
	resume_dir = resume_dir.expanduser()
	if not resume_dir.is_dir():
		emit_input_error(ctx, f"简历目录不存在: {resume_dir}")
		return

	processed: list[str] = []
	skipped: list[str] = []
	failed: list[dict[str, str]] = []
	for path in sorted(resume_dir.glob(pattern))[:limit]:
		if not path.is_file():
			continue
		try:
			record = evaluate_local(
				service=service, store=store, jd_text=jd_text, rubric=rubric,
				resume_payload=read_json_input(f"@{path}"), job_key=job_key,
				source={"type": "local", "path": str(path)}, save=True, force=force,
			)
			if record.get("skipped"):
				skipped.append(str(record.get("id", path.name)))
			else:
				processed.append(str(record.get("id", path.name)))
		except (RecruiterAIError, AIServiceError) as exc:
			failed.append({"file": str(path), "error": str(exc)})

	ranked_records = store.rank(job_key=job_key, top=max(top, draft_top))
	drafts: list[dict[str, Any]] = []
	draft_failed: list[dict[str, str]] = []
	if draft_top:
		drafts, draft_failed = draft_for_records(
			service=service, store=store, platform=None, records=ranked_records,
			limit=draft_top, include_chat=False, conversation_parser=conversation_to_text,
		)
	handle_output(
		ctx, "recruiter-ai-screen",
		{
			"job_key": job_key,
			"processed_count": len(processed),
			"skipped_unchanged_count": len(skipped),
			"failed_count": len(failed),
			"evaluation_ids": processed,
			"skipped_ids": skipped,
			"failed": failed,
			"ranking": summarize_ranking(ranked_records[:top]),
			"reply_drafts": drafts,
			"reply_draft_failures": draft_failed,
			"human_review_required": True,
		},
		hints={"next_actions": [
			f"boss hr ai report --job-key {job_key} --top {top}",
			"boss hr ai mark --evaluation-id <id> --status shortlisted",
		]},
	)


@click.command("batch", hidden=True)
@click.option("--jd", "jd_input", required=True)
@click.option("--resume-dir", required=True, type=click.Path(path_type=Path))
@click.option("--pattern", default="*.json")
@click.option("--job-key", required=True)
@click.option("--top", default=20, type=click.IntRange(1, 200))
@click.option("--limit", default=50, type=click.IntRange(1, 500))
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
	"""兼容旧版批量命令；保存岗位配置后转入 screen 工作流。"""
	try:
		RecruiterAIStore(ctx.obj["data_dir"]).save_job(
			job_key=job_key, jd_text=read_text_input(jd_input), rubric=normalize_rubric(),
		)
	except RecruiterAIError as exc:
		emit_input_error(ctx, str(exc))
		return
	ctx.invoke(
		screen_cmd, job_key=job_key, resume_dir=resume_dir, pattern=pattern,
		limit=limit, top=top, force=False, draft_top=0,
	)


@click.command("rank")
@click.option("--job-key", required=True, help="岗位唯一标识")
@click.option("--top", default=20, type=click.IntRange(1, 200), show_default=True)
@click.pass_context
def rank_cmd(ctx: click.Context, job_key: str, top: int) -> None:
	"""查看去重后的候选人排行榜。"""
	store = RecruiterAIStore(ctx.obj["data_dir"])
	ranking = summarize_ranking(store.rank(job_key=job_key, top=top))
	handle_output(
		ctx, "recruiter-ai-rank",
		{"job_key": job_key, "count": len(ranking), "ranking": ranking, "human_review_required": True},
		hints={"next_actions": [
			"boss hr ai reply --evaluation-id <id> --intent auto",
			"boss hr ai mark --evaluation-id <id> --status shortlisted",
		]},
	)


@click.command("report")
@click.option("--job-key", required=True, help="岗位唯一标识")
@click.option("--top", default=10, type=click.IntRange(1, 100), show_default=True)
@click.pass_context
def report_cmd(ctx: click.Context, job_key: str, top: int) -> None:
	"""输出最适合候选人、推荐分组和人工处理状态摘要。"""
	handle_output(
		ctx, "recruiter-ai-report",
		RecruiterAIStore(ctx.obj["data_dir"]).report(job_key=job_key, top=top),
		hints={"next_actions": [
			"查看 top_candidates 的证据、风险和待确认问题",
			"boss hr ai mark --evaluation-id <id> --status interview",
		]},
	)


@click.command("mark")
@click.option("--evaluation-id", required=True, help="评估记录 ID")
@click.option("--status", required=True, type=click.Choice(sorted(CANDIDATE_STATUSES)))
@click.option("--note", default="", help="人工处理备注")
@click.pass_context
def mark_cmd(ctx: click.Context, evaluation_id: str, status: str, note: str) -> None:
	"""人工标记候选人阶段，不执行平台写操作。"""
	try:
		record = RecruiterAIStore(ctx.obj["data_dir"]).set_status(evaluation_id, status, note=note)
	except RecruiterAIError as exc:
		emit_input_error(ctx, str(exc))
		return
	handle_output(ctx, "recruiter-ai-mark", record)


@click.command("reply")
@click.option("--evaluation-id", required=True, help="评估记录 ID")
@click.option("--conversation", default="", help="聊天上下文文本或 @文件路径；可省略")
@click.option(
	"--intent", default="auto", show_default=True,
	type=click.Choice(["auto", "acknowledge", "ask_followup", "invite_interview", "clarify", "decline_draft"]),
	help="回复目的",
)
@click.pass_context
def reply_cmd(ctx: click.Context, evaluation_id: str, conversation: str, intent: str) -> None:
	"""根据评估和聊天上下文生成待人工审核的回复草稿。"""
	service = service_for(ctx)
	if service is None:
		return
	store = RecruiterAIStore(ctx.obj["data_dir"])
	try:
		record = store.get_evaluation(evaluation_id)
		conversation_text = read_text_input(conversation) if conversation else ""
		evaluation, jd_text = record.get("evaluation"), record.get("jd_text")
		if not isinstance(evaluation, dict) or not isinstance(jd_text, str):
			raise RecruiterAIError(f"评估记录缺少必要字段: {evaluation_id}")
		resolved_intent = recommended_reply_intent(evaluation) if intent == "auto" else intent
		draft = generate_reply_draft(service, jd_text, evaluation, conversation_text, resolved_intent)
		reply_record = store.save_reply(
			evaluation_id=evaluation_id, intent=resolved_intent,
			conversation=conversation_text, draft=draft,
		)
	except RecruiterAIError as exc:
		emit_input_error(ctx, str(exc))
		return
	except AIServiceError as exc:
		emit_ai_error(ctx, "recruiter-ai-reply", exc)
		return
	handle_output(
		ctx, "recruiter-ai-reply", reply_record,
		hints={"next_actions": ["人工检查 draft.reply 后，再回到 BOSS 官方页面发送"]},
	)
