(() => {
	function isCandidateDetailMutation(path, method) {
		if (["GET", "HEAD"].includes(method)) return false;
		if (path === "/api/jobs" || path === "/api/candidates/bulk-status") return true;
		return /^\/api\/candidates\/[^/]+\/status$/.test(path);
	}

	const previousApi = api;
	api = function candidateCacheConsistentApi(path, options = {}) {
		const method = String(options.method || "GET").toUpperCase();
		return Promise.resolve(previousApi(path, options)).then(result => {
			if (isCandidateDetailMutation(path, method)) state.candidateDetails.clear();
			return result;
		});
	};

	const previousRenderScreenResult = renderScreenResult;
	renderScreenResult = function renderScreenResultWithFreshDetails(result) {
		// A completed screening run can create a new evaluation version and make previously cached
		// freshness/status metadata obsolete. Clear details before the user opens the new ranking.
		state.candidateDetails.clear();
		return previousRenderScreenResult(result);
	};
})();
