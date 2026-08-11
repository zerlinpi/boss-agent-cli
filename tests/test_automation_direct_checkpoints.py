import pytest

from boss_agent_cli.automation import direct_checkpoint as checkpoint
from boss_agent_cli.automation.config import AutomationConfig
from boss_agent_cli.automation.execution import process_pending
from boss_agent_cli.automation.models import (
	ActionResult,
	CandidateKey,
	Conversation,
	ConversationRef,
	Decision,
	EventStatus,
	PlatformAction,
)
from boss_agent_cli.automation.safety import SafetyGuard
from boss_agent_cli.automation.storage import AutomationStore


class Adapter:
	name = "mock"

	def __init__(self, *, fail: bool = False):
		self.fail = fail
		self.calls = 0

	def read_conversation(self, ref):
		return Conversation(title="candidate-1")

	def detect_safety_warning(self):
		return None

	def execute_action(self, action, message, ref):
		self.calls += 1
		if self.fail:
			raise RuntimeError("simulated direct-action crash")
		return ActionResult(status="executed")


def _decision() -> Decision:
	return Decision(
		action=PlatformAction.SEND_QUESTIONNAIRE,
		confidence=0.95,
		reason="high confidence",
		candidate_key=CandidateKey("candidate-1"),
		message="hello",
	)


def _install_decision(monkeypatch) -> None:
	monkeypatch.setattr(checkpoint, "decide_action", lambda *args, **kwargs: _decision())
	monkeypatch.setattr(checkpoint, "apply_reply_strategy", lambda decision, *args, **kwargs: decision)


def _crash_then_create_verification(store, monkeypatch) -> str:
	_install_decision(monkeypatch)
	state = store.read_state()
	with pytest.raises(RuntimeError):
		checkpoint.process_ref_checkpointed(
			Adapter(fail=True),
			store,
			AutomationConfig(),
			SafetyGuard(AutomationConfig(), state, dry_run=False),
			state,
			"mock",
			False,
			ConversationRef(id="ref-1", tab="new"),
		)
	restarted_state = store.read_state()
	checkpoint.process_ref_checkpointed(
		Adapter(),
		store,
		AutomationConfig(),
		SafetyGuard(AutomationConfig(), restarted_state, dry_run=False),
		restarted_state,
		"mock",
		False,
		ConversationRef(id="ref-1", tab="new"),
	)
	return store.read_reviews()[0].id


def test_direct_action_crash_leaves_durable_inflight_checkpoint(tmp_path, monkeypatch) -> None:
	_install_decision(monkeypatch)
	store = AutomationStore(tmp_path)
	state = store.read_state()
	guard = SafetyGuard(AutomationConfig(), state, dry_run=False)
	adapter = Adapter(fail=True)

	with pytest.raises(RuntimeError, match="direct-action crash"):
		checkpoint.process_ref_checkpointed(
			adapter,
			store,
			AutomationConfig(),
			guard,
			state,
			"mock",
			False,
			ConversationRef(id="ref-1", tab="new"),
		)

	persisted = store.read_state()
	assert persisted["conversations"]["candidate-1"]["inflight_action"]["action"] == "send_questionnaire"
	assert adapter.calls == 1


def test_restart_does_not_repeat_uncertain_direct_action(tmp_path, monkeypatch) -> None:
	_install_decision(monkeypatch)
	store = AutomationStore(tmp_path)
	state = store.read_state()
	guard = SafetyGuard(AutomationConfig(), state, dry_run=False)
	with pytest.raises(RuntimeError):
		checkpoint.process_ref_checkpointed(
			Adapter(fail=True), store, AutomationConfig(), guard, state, "mock", False,
			ConversationRef(id="ref-1", tab="new"),
		)

	restarted_state = store.read_state()
	adapter = Adapter()
	event = checkpoint.process_ref_checkpointed(
		adapter,
		store,
		AutomationConfig(),
		SafetyGuard(AutomationConfig(), restarted_state, dry_run=False),
		restarted_state,
		"mock",
		False,
		ConversationRef(id="ref-1", tab="new"),
	)

	assert adapter.calls == 0
	assert event.status == EventStatus.PLATFORM_VERIFICATION_REQUIRED.value
	assert any(review.id.startswith("verify-direct-") for review in store.read_reviews())


def test_successful_direct_action_updates_prior_and_clears_checkpoint(tmp_path, monkeypatch) -> None:
	_install_decision(monkeypatch)
	store = AutomationStore(tmp_path)
	state = store.read_state()
	adapter = Adapter()
	event = checkpoint.process_ref_checkpointed(
		adapter,
		store,
		AutomationConfig(),
		SafetyGuard(AutomationConfig(), state, dry_run=False),
		state,
		"mock",
		False,
		ConversationRef(id="ref-1", tab="new"),
	)

	persisted = store.read_state()["conversations"]["candidate-1"]
	assert event.status == EventStatus.AUTO_EXECUTED.value
	assert persisted["questionnaire_sent_at"]
	assert "inflight_action" not in persisted
	assert adapter.calls == 1


def test_dry_run_never_creates_direct_inflight_checkpoint(tmp_path, monkeypatch) -> None:
	_install_decision(monkeypatch)
	store = AutomationStore(tmp_path)
	state = store.read_state()
	adapter = Adapter()
	event = checkpoint.process_ref_checkpointed(
		adapter,
		store,
		AutomationConfig(),
		SafetyGuard(AutomationConfig(), state, dry_run=True),
		state,
		"mock",
		True,
		ConversationRef(id="ref-1", tab="new"),
	)

	assert event.status == EventStatus.DRY_RUN.value
	assert adapter.calls == 0
	assert "inflight_action" not in state["conversations"]["candidate-1"]


def test_approved_verification_retries_once_through_pending_and_clears_inflight(tmp_path, monkeypatch) -> None:
	store = AutomationStore(tmp_path)
	review_id = _crash_then_create_verification(store, monkeypatch)
	pending = store.approve_review(review_id, "2026-08-11T03:00:00+00:00")
	assert pending is not None

	state = store.read_state()
	adapter = Adapter()
	events = process_pending(
		store=store,
		state=state,
		adapters={"mock": adapter},
		guard=SafetyGuard(AutomationConfig(), state, dry_run=False),
		dry_run=False,
	)

	assert adapter.calls == 1
	assert events[-1].status == EventStatus.AUTO_EXECUTED.value
	persisted = store.read_state()["conversations"]["candidate-1"]
	assert persisted["questionnaire_sent_at"]
	assert "inflight_action" not in persisted
	assert store.read_pending()[0].status == "executed"


def test_rejected_verification_suppresses_retry_and_clears_inflight(tmp_path, monkeypatch) -> None:
	store = AutomationStore(tmp_path)
	review_id = _crash_then_create_verification(store, monkeypatch)
	rejected = store.reject_review(review_id, "confirmed already sent", "2026-08-11T03:00:00+00:00")
	assert rejected is not None

	state = store.read_state()
	adapter = Adapter()
	event = checkpoint.process_ref_checkpointed(
		adapter,
		store,
		AutomationConfig(),
		SafetyGuard(AutomationConfig(), state, dry_run=False),
		state,
		"mock",
		False,
		ConversationRef(id="ref-1", tab="new"),
	)

	assert adapter.calls == 0
	assert event.status == EventStatus.SKIPPED.value
	persisted = store.read_state()["conversations"]["candidate-1"]
	assert persisted["questionnaire_sent_at"] == "2026-08-11T03:00:00+00:00"
	assert "inflight_action" not in persisted
