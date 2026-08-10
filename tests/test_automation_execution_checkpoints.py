import pytest

from boss_agent_cli.automation.execution import process_pending
from boss_agent_cli.automation.models import EventStatus, PendingAction, PlatformAction
from boss_agent_cli.automation.storage import AutomationStore


class AllowGuard:
	def before_action(self, candidate_key, platform, action):
		return EventStatus.EXECUTED, "allowed"

	def record(self, candidate_key, action, status):
		return None

	def after_action(self, candidate_key, platform, action, status, outcome):
		return None


class Adapter:
	name = "mock"

	def __init__(self, *, fail=False):
		self.fail = fail
		self.calls = 0

	def send_questionnaire(self, ref, message):
		self.calls += 1
		if self.fail:
			raise RuntimeError("simulated crash after checkpoint")
		return EventStatus.EXECUTED, "sent"

	def send_follow_up(self, ref, message):
		return EventStatus.EXECUTED, "sent"

	def exchange_contact(self, ref):
		return EventStatus.EXECUTED, "exchanged"

	def create_interview_lead(self, ref, payload):
		return EventStatus.EXECUTED, "lead"


def _pending() -> PendingAction:
	return PendingAction(
		id="pending-1",
		candidate_key="candidate-1",
		platform="mock",
		action=PlatformAction.SEND_QUESTIONNAIRE,
		message="hello",
		payload={},
		approved_review_id="review-1",
		status="pending",
		created_at="2026-08-10T00:00:00+00:00",
	)


def test_pending_is_checkpointed_as_executing_before_side_effect(tmp_path) -> None:
	store = AutomationStore(tmp_path)
	store.write_pending([_pending()])
	adapter = Adapter(fail=True)

	with pytest.raises(RuntimeError, match="simulated crash"):
		process_pending(
			store=store,
			state={"conversations": {}, "autonomy": {}, "safety": {}},
			adapters={"mock": adapter},
			guard=AllowGuard(),
			dry_run=False,
		)

	assert store.read_pending()[0].status == "executing"
	assert adapter.calls == 1


def test_interrupted_pending_is_not_automatically_reexecuted(tmp_path) -> None:
	store = AutomationStore(tmp_path)
	item = _pending()
	item.status = "executing"
	store.write_pending([item])
	adapter = Adapter()

	events = process_pending(
		store=store,
		state={"conversations": {}, "autonomy": {}, "safety": {}},
		adapters={"mock": adapter},
		guard=AllowGuard(),
		dry_run=False,
	)

	assert adapter.calls == 0
	assert store.read_pending()[0].status == "verification-required"
	assert events[0].status == EventStatus.PLATFORM_VERIFICATION_REQUIRED
	assert any(review.id == "verify-pending-1" for review in store.read_reviews())


def test_dry_run_does_not_consume_pending_action(tmp_path) -> None:
	store = AutomationStore(tmp_path)
	store.write_pending([_pending()])
	adapter = Adapter()

	events = process_pending(
		store=store,
		state={"conversations": {}, "autonomy": {}, "safety": {}},
		adapters={"mock": adapter},
		guard=AllowGuard(),
		dry_run=True,
	)

	assert adapter.calls == 0
	assert store.read_pending()[0].status == "pending"
	assert events[0].status == EventStatus.DRY_RUN


def test_successful_pending_updates_candidate_prior_immediately(tmp_path) -> None:
	store = AutomationStore(tmp_path)
	store.write_pending([_pending()])
	adapter = Adapter()
	state = {"conversations": {}, "autonomy": {}, "safety": {}}

	process_pending(
		store=store,
		state=state,
		adapters={"mock": adapter},
		guard=AllowGuard(),
		dry_run=False,
	)

	assert store.read_pending()[0].status == "executed"
	persisted = store.read_state()
	assert persisted["conversations"]["candidate-1"]["questionnaire_sent_at"]
