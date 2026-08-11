from datetime import datetime, timezone

from boss_agent_cli.web import RecruiterWebController


def test_analytics_accepts_naive_and_zulu_timestamps_and_ignores_nonfinite_scores(tmp_path, monkeypatch) -> None:
	controller = RecruiterWebController(tmp_path)
	records = {
		"a": {
			"created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
			"evaluation": {"total_score": 80, "confidence": 0.8},
		},
		"b": {
			"created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
			"evaluation": {"total_score": float("nan"), "confidence": float("inf")},
		},
	}
	monkeypatch.setattr(controller.store, "latest_by_candidate", lambda **kwargs: records)
	monkeypatch.setattr(
		controller.store,
		"report",
		lambda **kwargs: {"status_counts": {"interview": "1", "hired": "bad"}},
	)

	result = controller.analytics("job")
	assert result["recent_7d"] == 2
	assert result["average_score"] == 80
	assert result["average_confidence"] == 0.8
	assert result["score_distribution"]["70-84"] == 1
	assert result["interview_conversion"] == 50.0
