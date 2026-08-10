(() => {
	function isCandidateDetailMutation(path, method) {
		if (["GET", "HEAD"].includes(method)) return false;
		if (path === "/api/jobs" || path === "/api/candidates/bulk-status") return true;
		return /^\/api\/candidates\/[^/]+\/status$/.test(path);
	}

	function clearCandidateSelection() {
		if (!state.selectedCandidates.size) return;
		state.selectedCandidates.clear();
		if (typeof updateBulkToolbar === "function") updateBulkToolbar();
	}

	const previousApi = api;
	api = function candidateCacheConsistentApi(path, options = {}) {
		const method = String(options.method || "GET").toUpperCase();
		return Promise.resolve(previousApi(path, options)).then(result => {
			if (isCandidateDetailMutation(path, method)) state.candidateDetails.clear();
			// Editing/deleting a job can change the active evaluation universe. Never keep selected
			// evaluation IDs across that boundary, because they may refer to stale or deleted versions.
			if (method !== "GET" && method !== "HEAD" && path === "/api/jobs") clearCandidateSelection();
			return result;
		});
	};

	const previousRenderScreenResult = renderScreenResult;
	renderScreenResult = function renderScreenResultWithFreshDetails(result) {
		// A completed screening run can create a new evaluation version and make previously cached
		// freshness/status metadata and selected evaluation IDs obsolete.
		state.candidateDetails.clear();
		clearCandidateSelection();
		return previousRenderScreenResult(result);
	};
})();
