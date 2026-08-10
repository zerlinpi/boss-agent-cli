from boss_agent_cli.web import RecruiterWebController
from boss_agent_cli.web.server import RecruiterWebApplication


def test_recruiter_app_asset_contains_write_deduplication_keyboard_freshness_and_multi_task_polling(tmp_path) -> None:
	application = RecruiterWebApplication(RecruiterWebController(tmp_path), token="fixed")
	try:
		content, content_type = application.asset("app.js")
		text = content.decode("utf-8")

		assert content_type.startswith("text/javascript")
		assert "inFlightWrites" in text
		assert "reliableApi" in text
		assert "taskPollers" in text
		assert "multiTaskWatch" in text
		assert "latestWatchedTask" in text
		assert "MAX_TASK_POLL_FAILURES" in text
		assert "entry.failures = 0" in text
		assert "state.taskCallbacks.delete(id)" in text
		assert "activeTasks" in text
		assert '["queued", "running", "cancelling"]' in text
		assert "MAX_CANDIDATE_DETAIL_CACHE" in text
		assert "pruneCandidateDetailCache" in text
		assert "candidateCacheConsistentApi" in text
		assert "renderScreenResultWithFreshDetails" in text
		assert "contextSafeDashboardLoad" in text
		assert "contextSafeCandidateListLoad" in text
		assert "contextSafeCandidateDetailLoad" in text
		assert "contextSafeJobEditorLoad" in text
		assert "dashboardRequestGeneration" in text
		assert "candidateDetailRequestGeneration" in text
		assert "safeAnalyzeJob" in text
		assert "jobAnalysisGeneration" in text
		assert "岗位内容已在分析期间发生变化" in text
		assert "accessibleRenderKanban" in text
		assert "aria-label" in text
		assert 'event.key === "Escape"' in text
		assert "drawerReturnFocus" in text
		assert "candidate-freshness-warning" in text
		assert "当前查看的是历史评估" in text
		assert "打开最新评估" in text
		assert "candidate-compare-title" in text
		assert "aria-modal" in text
		assert "comparisonReturnFocus" in text
		assert "关闭候选人对比" in text
	finally:
		application.tasks.close()
