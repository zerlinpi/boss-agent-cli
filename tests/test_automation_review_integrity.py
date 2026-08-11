from boss_agent_cli.automation.models import PlatformAction, ReviewItem
from boss_agent_cli.automation.storage import AutomationStore


def _review(review_id: str, candidate: str) -> ReviewItem:
	return ReviewItem(
		id=review_id,
		candidate_key=candidate,
		platform="zhipin",
		action=PlatformAction.SEND_FOLLOW_UP,
		message="hello",
		reason="review",
		decision_score=0.8,
		confidence=0.9,
		status="review",
		created_at="2026-08-11T00:00:00+00:00",
	)


def test_approving_one_review_preserves_all_other_reviews(tmp_path) -> None:
	store = AutomationStore(tmp_path)
	store.append_review(_review("review-1", "candidate-1"))
	store.append_review(_review("review-2", "candidate-2"))

	pending = store.approve_review("review-1", "2026-08-11T01:00:00+00:00")
	assert pending is not None

	reviews = {item.id: item for item in store.read_reviews()}
	assert set(reviews) == {"review-1", "review-2"}
	assert reviews["review-1"].status == "approved"
	assert reviews["review-2"].status == "review"
	assert [item.id for item in store.read_pending()] == ["review-1"]
