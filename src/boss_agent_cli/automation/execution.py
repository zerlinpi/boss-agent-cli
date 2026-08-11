"""Automation execution primitives."""

from __future__ import annotations

import inspect
from dataclasses import asdict
from typing import Any

from boss_agent_cli.automation.adapters import RecruiterAutomationPlatform
from boss_agent_cli.automation.config import AutomationConfig
from boss_agent_cli.automation.decision import decide_action
from boss_agent_cli.automation.events import make_event, now_iso, stable_action_id
from boss_agent_cli.automation.models import (
	AutomationEvent,
	AutomationMode,
	CandidateKey,
	ConversationRef,
	Decision,
	EventStatus,
	PendingAction,
	PlatformAction,
	ReviewItem,
)
from boss_agent_cli.automation.reply_ai import apply_reply_strategy
from boss_agent_cli.automation.safety import SafetyGuard
from boss_agent_cli.automation.storage import AutomationStore


def process_pending(
	adapter: RecruiterAutomationPlatform | None = None,
	store: AutomationStore | None = None,
	guard: Any = None,
	platform: str | None = None,
	dry_run: bool = False,
	*,
	state: dict[str, Any] | None = None,
	adapters: dict[str, Any] | None = None,
) -> list[AutomationEvent]:
	"""Process approved actions with a durable pre-side-effect checkpoint.

	The legacy single-adapter call shape remains supported. New callers should pass
	``state`` and ``adapters`` so the same state object is updated immediately after
	a confirmed external action.
	"""
	if store is None:
		raise TypeError("store is required")
	if adapters is None:
		if adapter is None or platform is None:
			raise TypeError("adapter and platform are required")
		adapters = {platform: adapter}
	if state is None:
		state = store.read_state()
	return _process_pending_checkpointed(
		store=store,
		state=state,
		adapters=adapters,
		guard=guard,
		dry_run=dry_run,
	)


def _process_pending_checkpointed(
	*,
	store: AutomationStore,
	state: dict[str, Any],
	adapters: dict[str, Any],
	guard: Any,
	dry_run: bool,
) -> list[AutomationEvent]:
	actions = store.read_pending()
	events: list[AutomationEvent] = []
	for index, item in enumerate(actions):
		if item.status == "executing":
			item.status = "verification-required"
			item.updated_at = now_iso()
			store.write_pending(actions)
			_review_interrupted_action(store, item)
			event = make_event(
				item.platform,
				item.candidate_key,
				PlatformAction(item.action),
				EventStatus.PLATFORM_VERIFICATION_REQUIRED,
				item.confidence,
				"上次进程在外部动作执行后未能确认结果，需要人工核验后再决定是否重试",
			)
			store.append_event(event)
			events.append(event)
			continue
		if item.status != "pending":
			continue
		adapter = adapters.get(item.platform)
		if adapter is None:
			continue
		action = PlatformAction(item.action)
		decision = Decision(
			action=action,
			confidence=item.confidence,
			reason=item.reason,
			candidate_key=CandidateKey(item.candidate_key),
			message=item.message,
		)
		allowed, gate_status, gate_reason = _guard_before(guard, adapter, item, decision)
		if not allowed:
			event = make_event(
				item.platform,
				item.candidate_key,
				action,
				gate_status,
				item.confidence,
				gate_reason,
			)
			store.append_event(event)
			events.append(event)
			continue
		if dry_run:
			event = make_event(
				item.platform,
				item.candidate_key,
				action,
				EventStatus.DRY_RUN,
				item.confidence,
				item.reason,
			)
			store.append_event(event)
			events.append(event)
			continue

		# Persist the uncertainty checkpoint before invoking a platform side effect.
		item.status = "executing"
		item.updated_at = now_iso()
		store.write_pending(actions)

		status, outcome = _execute_pending_action(adapter, item, action)
		if _execution_succeeded(status):
			item.status = "executed"
			item.updated_at = now_iso()
			store.write_pending(actions)
			_update_state_prior(state, item.candidate_key, action)
			store.write_state(state)
			_guard_after(guard, item, decision, EventStatus.AUTO_EXECUTED, outcome)
			event_status = EventStatus.AUTO_EXECUTED
		else:
			# A platform-confirmed failure can be retried later; an exception above is not
			# caught and therefore intentionally leaves the item in `executing`.
			item.status = "pending"
			item.updated_at = now_iso()
			store.write_pending(actions)
			_guard_failure(guard, item, action, outcome)
			event_status = EventStatus.STOPPED_BY_SAFETY
		event = make_event(
			item.platform,
			item.candidate_key,
			action,
			event_status,
			item.confidence,
			outcome or item.reason,
		)
		store.append_event(event)
		events.append(event)
		# Keep the local variable synchronized with the list element for dataclass callers.
		actions[index] = item
	return events


def _guard_before(guard: Any, adapter: Any, item: PendingAction, decision: Decision) -> tuple[bool, EventStatus, str]:
	if guard is None:
		return True, EventStatus.EXECUTED, "allowed"
	method = getattr(guard, "before_action", None)
	if method is None:
		return True, EventStatus.EXECUTED, "allowed"
	try:
		parameter_count = len(inspect.signature(method).parameters)
	except (TypeError, ValueError):
		parameter_count = 2
	if parameter_count >= 3:
		result = method(item.candidate_key, item.platform, PlatformAction(item.action))
		if isinstance(result, tuple) and result:
			status = result[0]
			reason = str(result[1]) if len(result) > 1 else ""
			if status in {EventStatus.EXECUTED, EventStatus.AUTO_EXECUTED, "EXECUTED", "executed"}:
				return True, EventStatus.EXECUTED, reason
			try:
				return False, EventStatus(status), reason
			except (TypeError, ValueError):
				return False, EventStatus.STOPPED_BY_SAFETY, reason or str(status)
	warning_method = getattr(adapter, "detect_safety_warning", None)
	warning = warning_method() if callable(warning_method) else ""
	result = method(decision, warning or "")
	if getattr(result, "allowed", False):
		return True, EventStatus.EXECUTED, str(getattr(result, "reason", ""))
	reason = str(getattr(result, "reason", "blocked by safety guard"))
	if getattr(result, "circuit_breaker", False):
		open_breaker = getattr(guard, "open_circuit_breaker", None)
		if callable(open_breaker):
			open_breaker(reason)
		return False, EventStatus.CIRCUIT_BREAKER_OPEN, reason
	return False, EventStatus.STOPPED_BY_SAFETY, reason


def _execute_pending_action(adapter: Any, item: PendingAction, action: PlatformAction) -> tuple[Any, str]:
	ref = ConversationRef(id=item.candidate_key, tab="pending")
	if action is PlatformAction.SEND_QUESTIONNAIRE and hasattr(adapter, "send_questionnaire"):
		result = adapter.send_questionnaire(ref, item.message)
	elif action is PlatformAction.SEND_FOLLOW_UP and hasattr(adapter, "send_follow_up"):
		result = adapter.send_follow_up(ref, item.message)
	elif action is PlatformAction.EXCHANGE_CONTACT and hasattr(adapter, "exchange_contact"):
		result = adapter.exchange_contact(ref)
	elif action is PlatformAction.CREATE_INTERVIEW_LEAD and hasattr(adapter, "create_interview_lead"):
		result = adapter.create_interview_lead(ref, item.payload)
	else:
		result = adapter.execute_action(action, item.message, ref)
	if isinstance(result, tuple):
		status = result[0] if result else ""
		return status, str(result[1]) if len(result) > 1 else str(status)
	status = getattr(result, "status", "")
	details = getattr(result, "details", {})
	if isinstance(details, dict):
		reason = str(details.get("reason", status))
	else:
		reason = str(status)
	return status, reason


def _execution_succeeded(status: Any) -> bool:
	if isinstance(status, EventStatus):
		return status in {EventStatus.EXECUTED, EventStatus.AUTO_EXECUTED}
	return str(status).casefold() in {"executed", "auto_executed"}


def _update_state_prior(state: dict[str, Any], candidate_key: str, action: PlatformAction) -> None:
	prior = state.setdefault("conversations", {}).setdefault(candidate_key, {})
	now = now_iso()
	if action is PlatformAction.SEND_QUESTIONNAIRE:
		prior["questionnaire_sent_at"] = now
	elif action is PlatformAction.SEND_FOLLOW_UP:
		prior["follow_up_sent_at"] = now
	elif action is PlatformAction.EXCHANGE_CONTACT:
		prior["exchange_contact_at"] = now
	elif action is PlatformAction.CREATE_INTERVIEW_LEAD:
		prior["interview_lead_created_at"] = now
	prior.pop("inflight_action", None)


def _review_interrupted_action(store: AutomationStore, item: PendingAction) -> None:
	review_id = f"verify-{item.id}"
	if any(review.id == review_id for review in store.read_reviews()):
		return
	store.append_review(ReviewItem(
		id=review_id,
		candidate_key=item.candidate_key,
		platform=item.platform,
		action=PlatformAction(item.action),
		message=item.message,
		reason="外部动作结果未知；请先在平台确认是否已执行，再决定批准重试或拒绝",
		decision_score=item.decision_score,
		confidence=item.confidence,
		payload=dict(item.payload),
		status="review",
		created_at=now_iso(),
	))


def _guard_after(guard: Any, item: PendingAction, decision: Decision, status: EventStatus, outcome: str) -> None:
	if guard is None:
		return
	method = getattr(guard, "after_action", None)
	if method is None:
		return
	try:
		parameter_count = len(inspect.signature(method).parameters)
	except (TypeError, ValueError):
		parameter_count = 1
	if parameter_count >= 5:
		method(item.candidate_key, item.platform, PlatformAction(item.action), status, outcome)
	else:
		method(decision)


def _guard_failure(guard: Any, item: PendingAction, action: PlatformAction, reason: str) -> None:
	if guard is None:
		return
	record = getattr(guard, "record", None)
	if callable(record):
		record(item.candidate_key, action, EventStatus.STOPPED_BY_SAFETY)
		return
	record_failure = getattr(guard, "record_failure", None)
	if callable(record_failure):
		record_failure(reason)


def process_ref(
	adapter: RecruiterAutomationPlatform,
	store: AutomationStore,
	config: AutomationConfig,
	guard: SafetyGuard,
	state: dict[str, Any],
	platform: str,
	dry_run: bool,
	ref: ConversationRef,
) -> AutomationEvent:
	conversation = adapter.read_conversation(ref)
	candidate_key = conversation.title or str(conversation.fingerprint) or ref.id
	prior = state.setdefault("conversations", {}).setdefault(candidate_key, {})
	decision = decide_action(conversation, config, prior)
	decision = apply_reply_strategy(decision, conversation, config, store.root.parent)
	status = status_for_decision(config, decision, dry_run)
	event_reason = decision.reason
	if decision.action is PlatformAction.CREATE_INTERVIEW_LEAD and status in {
		EventStatus.AUTO_EXECUTED,
		EventStatus.DRY_RUN,
	}:
		store.append_interview_lead(candidate_key, decision.interview_time, decision.reason)
	elif status is EventStatus.AUTO_EXECUTED or status is EventStatus.DRY_RUN:
		status, event_reason = execute_or_dry_run(adapter, guard, decision, ref, dry_run)
		if status in {EventStatus.AUTO_EXECUTED, EventStatus.DRY_RUN}:
			update_prior(prior, decision)
	elif status is EventStatus.QUEUED_FOR_REVIEW:
		store.append_review(_review_item(platform, candidate_key, decision))
	elif status is EventStatus.QUEUED_PENDING_ACTION:
		store.append_pending(_pending_action(platform, candidate_key, decision, ""))
	event = make_event(
		platform,
		candidate_key,
		decision.action,
		status,
		decision.confidence,
		event_reason,
	)
	store.append_event(event)
	return event


def status_for_decision(config: AutomationConfig, decision: Decision, dry_run: bool) -> EventStatus:
	match decision.action:
		case PlatformAction.SKIP:
			return EventStatus.SKIPPED
		case PlatformAction.CREATE_INTERVIEW_LEAD:
			return _lead_status(config, decision, dry_run)
		case _:
			return _action_status(config, decision, dry_run)


def execute_or_dry_run(
	adapter: RecruiterAutomationPlatform,
	guard: SafetyGuard,
	decision: Decision,
	ref: ConversationRef,
	dry_run: bool,
) -> tuple[EventStatus, str]:
	safety = guard.before_action(decision, adapter.detect_safety_warning() or "")
	if not safety.allowed:
		if safety.circuit_breaker:
			guard.open_circuit_breaker(safety.reason)
			return EventStatus.CIRCUIT_BREAKER_OPEN, safety.reason
		return EventStatus.STOPPED_BY_SAFETY, safety.reason
	if dry_run:
		return EventStatus.DRY_RUN, decision.reason
	result = adapter.execute_action(decision.action, decision.message, ref)
	if result.status != "executed":
		reason = str(result.details.get("reason", result.status))
		guard.record_failure(reason)
		return EventStatus.STOPPED_BY_SAFETY, reason
	guard.after_action(decision)
	return EventStatus.AUTO_EXECUTED, decision.reason


def update_prior(prior: dict[str, str], decision: Decision) -> None:
	match decision.action:
		case PlatformAction.SEND_QUESTIONNAIRE:
			prior["questionnaire_sent_at"] = now_iso()
		case PlatformAction.SEND_FOLLOW_UP:
			prior["follow_up_sent_at"] = now_iso()
		case PlatformAction.EXCHANGE_CONTACT:
			prior["exchange_contact_at"] = now_iso()
		case _:
			return


def _common_gate(config: AutomationConfig, decision: Decision) -> EventStatus | None:
	if decision.requires_human or decision.risk_flags:
		return EventStatus.QUEUED_FOR_REVIEW
	if config.mode in {AutomationMode.ASSIST, AutomationMode.TRAINING}:
		return EventStatus.QUEUED_FOR_REVIEW
	if decision.confidence < config.human_review_threshold:
		return EventStatus.SKIPPED
	return None


def _lead_status(config: AutomationConfig, decision: Decision, dry_run: bool) -> EventStatus:
	gated = _common_gate(config, decision)
	if gated is not None:
		return gated
	if decision.action not in config.allowed_actions:
		return EventStatus.QUEUED_PENDING_ACTION
	return EventStatus.DRY_RUN if dry_run else EventStatus.AUTO_EXECUTED


def _action_status(config: AutomationConfig, decision: Decision, dry_run: bool) -> EventStatus:
	gated = _common_gate(config, decision)
	if gated is not None:
		return gated
	if decision.confidence < config.auto_execute_threshold:
		return EventStatus.QUEUED_FOR_REVIEW
	if decision.action not in config.allowed_actions:
		return EventStatus.QUEUED_PENDING_ACTION
	return EventStatus.DRY_RUN if dry_run else EventStatus.AUTO_EXECUTED


def _review_item(platform: str, candidate_key: str, decision: Decision) -> ReviewItem:
	ts = now_iso()
	return ReviewItem(
		id=stable_action_id(platform, candidate_key, decision.action, ts),
		created_at=ts,
		platform=platform,
		candidate_key=candidate_key,
		action=decision.action,
		status="review",
		decision_score=decision.confidence,
		confidence=decision.confidence,
		reason=decision.reason,
		message=decision.message,
	)


def _pending_action(
	platform: str,
	candidate_key: str,
	decision: Decision,
	approved_review_id: str,
) -> PendingAction:
	ts = now_iso()
	return PendingAction(
		id=stable_action_id(platform, candidate_key, decision.action, ts),
		created_at=ts,
		platform=platform,
		candidate_key=candidate_key,
		action=decision.action,
		status="pending",
		decision_score=decision.confidence,
		confidence=decision.confidence,
		reason=decision.reason,
		message=decision.message,
		approved_review_id=approved_review_id,
	)


def _pending_with_status(item: PendingAction, status: str) -> PendingAction:
	values = asdict(item)
	values["status"] = status
	values["updated_at"] = now_iso()
	return PendingAction(**values)


def _next_pending_status(status: EventStatus) -> str:
	match status:
		case EventStatus.AUTO_EXECUTED:
			return "executed"
		case EventStatus.DRY_RUN:
			return "pending"
		case _:
			return "pending"
