import datetime
from typing import Any

from boss_agent_cli.commands.chat_utils import RELATION_LABELS


_FOLLOW_UP_STATES = {"reply_needed", "follow_up", "interview"}


def _nonnegative_int(value: Any) -> int:
	if isinstance(value, bool):
		return 0
	try:
		return max(0, int(value))
	except (TypeError, ValueError, OverflowError):
		return 0


def _text(value: Any, default: str = "-") -> str:
	if value is None:
		return default
	text = str(value).strip()
	return text or default


def _ts_to_label(value: Any) -> str:
	ts_ms = _nonnegative_int(value)
	if not ts_ms:
		return "-"
	try:
		dt = datetime.datetime.fromtimestamp(ts_ms / 1000)
	except (OSError, OverflowError, ValueError):
		return "-"
	return dt.strftime("%m-%d %H:%M")


def _chat_stage(item: dict[str, Any], *, now_ts_ms: int, stale_days: int) -> str:
	unread = _nonnegative_int(item.get("unreadMsgCount"))
	relation_type = _nonnegative_int(item.get("relationType"))
	last_ts = _nonnegative_int(item.get("lastTS"))
	now = _nonnegative_int(now_ts_ms)
	days = _nonnegative_int(stale_days)
	if unread > 0:
		return "reply_needed"
	if relation_type == 3:
		return "applied"
	if last_ts and now >= last_ts and now - last_ts >= days * 24 * 3600 * 1000:
		return "follow_up"
	return "chatting"


def build_pipeline_items(
	*,
	chat_items: list[dict[str, Any]],
	interview_items: list[dict[str, Any]],
	now_ts_ms: int,
	stale_days: int = 3,
) -> list[dict[str, Any]]:
	items: list[dict[str, Any]] = []

	for raw in chat_items:
		if not isinstance(raw, dict):
			continue
		stage = _chat_stage(raw, now_ts_ms=now_ts_ms, stale_days=stale_days)
		unread = _nonnegative_int(raw.get("unreadMsgCount"))
		relation_type = _nonnegative_int(raw.get("relationType"))
		items.append(
			{
				"source": "chat",
				"stage": stage,
				"security_id": _text(raw.get("securityId"), ""),
				"job_id": _text(raw.get("encryptJobId"), ""),
				"company": _text(raw.get("brandName")),
				"title": _text(raw.get("title")),
				"relation": RELATION_LABELS.get(relation_type, "未知"),
				"unread": unread,
				"last_msg": _text(raw.get("lastMsg")),
				"last_time": _ts_to_label(raw.get("lastTS")),
				"reason": "存在未读消息" if unread > 0 else "需要继续推进" if stage == "follow_up" else "会话进行中",
			}
		)

	for raw in interview_items:
		if not isinstance(raw, dict):
			continue
		items.append(
			{
				"source": "interview",
				"stage": "interview",
				"security_id": _text(raw.get("securityId"), ""),
				"job_id": _text(raw.get("encryptJobId"), ""),
				"company": _text(raw.get("brandName")),
				"title": _text(raw.get("jobName")),
				"relation": "面试",
				"unread": 0,
				"last_msg": _text(raw.get("statusDesc")),
				"last_time": _text(raw.get("interviewTime")),
				"reason": "存在待处理面试安排",
			}
		)

	priority = {"reply_needed": 0, "interview": 1, "follow_up": 2, "applied": 3, "chatting": 4}
	return sorted(
		items,
		key=lambda item: (
			priority.get(str(item.get("stage")), 99),
			str(item.get("company", "-")),
			str(item.get("title", "-")),
		),
	)


def select_follow_up_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
	return [item for item in items if item.get("stage") in _FOLLOW_UP_STATES]
