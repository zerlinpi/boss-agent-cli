import json

import pytest

from boss_agent_cli.automation.models import PendingAction, PlatformAction, ReviewItem
from boss_agent_cli.automation.storage import AutomationStorageError, AutomationStore


def _review() -> ReviewItem:
	return ReviewItem(
		id="review-1",
		candidate_key="candidate-1",
		platform="mock",
		action=PlatformAction.SEND_FOLLOW_UP,
		message="follow up",
		reason="test",
		decision_score=0.8,
		confidence=0.9,
		payload={"x": 1},
		created_at="2026-08-10T00:00:00+00:00",
	)


def test_persisted_actions_rehydrate_platform_action_enum(tmp_path) -> None:
	store = AutomationStore(tmp_path)
	store.append_review(_review())
	store.append_pending(PendingAction(
		id="pending-1",
		candidate_key="candidate-1",
		platform="mock",
		action=PlatformAction.EXCHANGE_CONTACT,
		message="",
		payload={},
		approved_review_id="review-1",
		status="pending",
		created_at="2026-08-10T00:00:00+00:00",
	))

	assert store.read_reviews()[0].action is PlatformAction.SEND_FOLLOW_UP
	assert store.read_pending()[0].action is PlatformAction.EXCHANGE_CONTACT


def test_corrupt_authoritative_state_fails_closed(tmp_path) -> None:
	store = AutomationStore(tmp_path)
	store.state_path.write_text("{not-json", encoding="utf-8")
	with pytest.raises(AutomationStorageError, match="state.json 损坏"):
		store.read_state()


def test_corrupt_jsonl_reports_file_and_line(tmp_path) -> None:
	store = AutomationStore(tmp_path)
	store.review_path.write_text('{}\n{not-json\n', encoding="utf-8")
	with pytest.raises(AutomationStorageError, match="第 2 行"):
		store.read_reviews()


def test_approval_transaction_is_recovered_without_duplicate_pending(tmp_path) -> None:
	store = AutomationStore(tmp_path)
	review = _review()
	approved = _review()
	approved.status = "approved"
	approved.reviewed_at = "2026-08-10T01:00:00+00:00"
	pending = PendingAction(
		id="pending-review-1",
		candidate_key=review.candidate_key,
		platform=review.platform,
		action=review.action,
		message=review.message,
		payload=review.payload,
		approved_review_id=review.id,
		status="pending",
		created_at=approved.reviewed_at,
	)
	store.review_path.write_text(json.dumps(review.__dict__, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
	store._approval_tx_path.write_text(
		json.dumps({
			"reviews": [{**approved.__dict__, "action": approved.action.value}],
			"pending_action": {**pending.__dict__, "action": pending.action.value},
		}, ensure_ascii=False),
		encoding="utf-8",
	)

	rows = store.read_pending()
	assert [item.id for item in rows] == ["pending-review-1"]
	assert store.read_reviews()[0].status == "approved"
	assert not store._approval_tx_path.exists()

	# A second read must not replay the recovered transaction or duplicate the action.
	assert [item.id for item in store.read_pending()] == ["pending-review-1"]
