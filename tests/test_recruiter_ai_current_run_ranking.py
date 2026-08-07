from boss_agent_cli.commands.recruiter.ai_common import ranked_records_for_run


class FakeStore:
	def __init__(self, records):
		self.records = records
		self.calls = []

	def rank(self, *, job_key, top):
		self.calls.append((job_key, top))
		return self.records[:top]


def test_draft_ranking_filters_to_current_run_after_full_bounded_rank() -> None:
	records = [
		{"id": "old-high", "evaluation": {"total_score": 99}},
		{"id": "new-mid", "evaluation": {"total_score": 80}},
		{"id": "old-low", "evaluation": {"total_score": 60}},
	]
	store = FakeStore(records)

	ranked, current = ranked_records_for_run(
		store,  # type: ignore[arg-type]
		job_key="java",
		top=1,
		draft_top=1,
		processed_ids=["new-mid"],
	)

	assert store.calls == [("java", 10_000)]
	assert [record["id"] for record in ranked] == ["old-high", "new-mid", "old-low"]
	assert [record["id"] for record in current] == ["new-mid"]


def test_unchanged_run_has_no_current_run_draft_candidates() -> None:
	store = FakeStore([{"id": "old-high"}, {"id": "old-low"}])

	ranked, current = ranked_records_for_run(
		store,  # type: ignore[arg-type]
		job_key="java",
		top=1,
		draft_top=5,
		processed_ids=[],
	)

	assert store.calls == [("java", 1)]
	assert [record["id"] for record in ranked] == ["old-high"]
	assert current == []
