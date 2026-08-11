"""Crash-safe checkpointing for direct automation decisions."""

from __future__ import annotations

from typing import Any

from boss_agent_cli.automation.config import AutomationConfig
from boss_agent_cli.automation.decision import decide_action
from boss_agent_cli.automation.events import make_event, now_iso, stable_action_id
from boss_agent_cli.automation.execution import _pending_action, _review_item, status_for_decision, update_prior
from boss_agent_cli.automation.models import (
	AutomationEvent,
	ConversationRef,
	Decision,
	EventStatus,
	PlatformAction,
	ReviewItem,
)
from boss_agent_cli.automation.reply_ai import apply_reply_strategy
from boss_agent_cli.automation.safety import SafetyGuard
from boss_agent_cli.automation.storage import AutomationStore


def _marker_for(action: PlatformAction) -> str:
	return {
		PlatformAction.SEND_QUESTIONNAIRE: "questionnaire_sent_at",
		PlatformAction.SEND_FOLLOW_UP: "follow_up_sent_at",
		PlatformAction.EXCHANGE_CONTACT: "exchange_contact_at",
		PlatformAction.CREATE_INTERVIEW_LEAD: "interview_lead_created_at",
	}.get(action, "last_verified_action_at")


def _verification_review(
	store: AutomationStore,
	*,
	platform: str,
	candidate_key: str,
	inflight: dict[str, Any],
) -> ReviewItem:
	action = PlatformAction(str(inflight.get("action") or ""))
	review_id = str(inflight.get("verification_review_id") or "")
	if not review_id:
		review_id = f"verify-direct-{stable_action_id(platform, candidate_key, action, str(inflight.get('started_at') or 'unknown'))}"
	for review in store.read_reviews():
		if review.id == review_id:
			return review
	item = ReviewItem(
		id=review_id,
		candidate_key=candidate_key,
		platform=platform,
		action=action,
		message=str(inflight.get("message") or ""),
		reason="上次进程在直接外部动作后未能确认结果；请先在平台核验是否已经执行，再决定批准重试或拒绝",
		decision_score=float(inflight.get("confidence") or 0.0),
		confidence=float(inflight.get("confidence") or 0.0),
		payload={"checkpoint": "direct", "started_at": inflight.get("started_at")},
		status="review",
		created_at=now_iso(),
	)
	store.append_review(item)
	return item


def _handle_existing_inflight(
	store: AutomationStore,
	state: dict[str, Any],
	prior: dict[str, Any],
	*,
	platform: str,
	candidate_key: str,
) -> AutomationEvent:
	inflight = prior.get("inflight_action")
	if not isinstance(inflight, dict):
		raise TypeError("inflight_action must be an object")
	action = PlatformAction(str(inflight.get("action") or ""))
	review = _verification_review(
		store,
		platform=platform,
		candidate_key=candidate_key,
		inflight=inflight,
	)
	inflight["verification_review_id"] = review.id
	inflight["status"] = "verification-required"

	if review.status == "rejected":
		prior[_marker_for(action)] = review.reviewed_at or now_iso()
		prior.pop("inflight_action", None)
		store.write_state(state)
		status = EventStatus.SKIPPED
		reason = "人工核验后拒绝重试未知结果的外部动作"
	else:
		store.write_state(state)
		status = EventStatus.PLATFORM_VERIFICATION_REQUIRED
		reason = "存在结果未知的上次外部动作；本轮不自动重试"

	event = make_event(platform, candidate_key, action, status, review.confidence, reason)
	store.append_event(event)
	return event


def _blocked_event(
	store: AutomationStore,
	guard: SafetyGuard,
	platform: str,
	candidate_key: str,
	decision: Decision,
	warning: str,
) -> AutomationEvent | None:
	safety = guard.before_action(decision, warning)
	if safety.allowed:
		return None
	if safety.circuit_breaker:
		guard.open_circuit_breaker(safety.reason)
		status = EventStatus.CIRCUIT_BREAKER_OPEN
	else:
		status = EventStatus.STOPPED_BY_SAFETY
	event = make_event(platform, candidate_key, decision.action, status, decision.confidence, safety.reason)
	store.append_event(event)
	return event


def process_ref_checkpointed(
	adapter: Any,
	store: AutomationStore,
	config: AutomationConfig,
	guard: SafetyGuard,
	state: dict[str, Any],
	platform: str,
	dry_run: bool,
	ref: ConversationRef,
) -> AutomationEvent:
	"""Process one conversation without blindly retrying an uncertain side effect."""
	conversation = adapter.read_conversation(ref)
	candidate_key = conversation.title or str(conversation.fingerprint) or ref.id
	conversations = state.setdefault("conversations", {})
	if not isinstance(conversations, dict):
		raise TypeError("state.conversations must be an object")
	prior = conversations.setdefault(candidate_key, {})
	if not isinstance(prior, dict):
		raise TypeError("candidate prior must be an object")

	if isinstance(prior.get("inflight_action"), dict):
		return _handle_existing_inflight(
			store,
			state,
			prior,
			platform=platform,
			candidate_key=candidate_key,
		)

	decision = decide_action(conversation, config, prior)
	decision = apply_reply_strategy(decision, conversation, config, store.root.parent)
	status = status_for_decision(config, decision, dry_run)

	if status is EventStatus.QUEUED_FOR_REVIEW:
		store.append_review(_review_item(platform, candidate_key, decision))
		event = make_event(platform, candidate_key, decision.action, status, decision.confidence, decision.reason)
		store.append_event(event)
		return event
	if status is EventStatus.QUEUED_PENDING_ACTION:
		store.append_pending(_pending_action(platform, candidate_key, decision, ""))
		event = make_event(platform, candidate_key, decision.action, status, decision.confidence, decision.reason)
		store.append_event(event)
		return event
	if status is EventStatus.SKIPPED:
		event = make_event(platform, candidate_key, decision.action, status, decision.confidence, decision.reason)
		store.append_event(event)
		return event
	if status is EventStatus.DRY_RUN:
		event = make_event(platform, candidate_key, decision.action, status, decision.confidence, decision.reason)
		store.append_event(event)
		return event

	if status is not EventStatus.AUTO_EXECUTED:
		event = make_event(platform, candidate_key, decision.action, status, decision.confidence, decision.reason)
		store.append_event(event)
		return event

	warning = adapter.detect_safety_warning() or ""
	blocked = _blocked_event(store, guard, platform, candidate_key, decision, warning)
	if blocked is not None:
		return blocked

	started_at = now_iso()
	review_id = f"verify-direct-{stable_action_id(platform, candidate_key, decision.action, started_at)}"
	prior["inflight_action"] = {
		"action": decision.action.value,
		"started_at": started_at,
		"message": decision.message,
		"reason": decision.reason,
		"confidence": decision.confidence,
		"verification_review_id": review_id,
		"status": "executing",
	}
	store.write_state(state)

	if decision.action is PlatformAction.CREATE_INTERVIEW_LEAD:
		store.append_interview_lead(candidate_key, decision.interview_time, decision.reason)
		prior["interview_lead_created_at"] = now_iso()
		prior.pop("inflight_action", None)
		store.write_state(state)
		guard.after_action(decision)
		event = make_event(
			platform,
			candidate_key,
			decision.action,
			EventStatus.AUTO_EXECUTED,
			decision.confidence,
			decision.reason,
		)
		store.append_event(event)
		return event

	result = adapter.execute_action(decision.action, decision.message, ref)
	if result.status != "executed":
		reason = str(result.details.get("reason", result.status))
		guard.record_failure(reason)
		prior.pop("inflight_action", None)
		store.write_state(state)
		event = make_event(
			platform,
			candidate_key,
			decision.action,
			EventStatus.STOPPED_BY_SAFETY,
			decision.confidence,
			reason,
		)
		store.append_event(event)
		return event

	guard.after_action(decision)
	update_prior(prior, decision)
	prior.pop("inflight_action", None)
	store.write_state(state)
	event = make_event(
		platform,
		candidate_key,
		decision.action,
		EventStatus.AUTO_EXECUTED,
		decision.confidence,
		decision.reason,
	)
	store.append_event(event)
	return event
