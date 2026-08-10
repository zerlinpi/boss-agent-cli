(() => {
	let dashboardRequestGeneration = 0;
	let candidateListRequestGeneration = 0;
	let candidateDetailRequestGeneration = 0;
	let jobEditRequestGeneration = 0;
	const MAX_DETAIL_CACHE = 100;

	function touchDetailCache(id, detail) {
		state.candidateDetails.delete(id);
		state.candidateDetails.set(id, detail);
		while (state.candidateDetails.size > MAX_DETAIL_CACHE) {
			const oldest = state.candidateDetails.keys().next().value;
			if (oldest === undefined) break;
			state.candidateDetails.delete(oldest);
		}
	}

	loadDashboard = async function contextSafeDashboardLoad() {
		const generation = ++dashboardRequestGeneration;
		const jobKey = state.activeJob;
		if (!jobKey) {
			renderEmptyDashboard();
			return;
		}
		try {
			const data = await api(`/api/candidates?job_key=${encodeURIComponent(jobKey)}&top=500`);
			if (generation !== dashboardRequestGeneration || state.activeJob !== jobKey) return;
			state.candidates = data.items || [];
			renderDashboard(data.report || {}, data.analytics || {});
			renderCandidateViews();
		} catch (error) {
			if (generation === dashboardRequestGeneration && state.activeJob === jobKey) {
				toast(error.message, "error");
			}
		}
	};

	loadCandidates = async function contextSafeCandidateListLoad() {
		const generation = ++candidateListRequestGeneration;
		const jobKey = state.activeJob;
		if (!jobKey) {
			state.candidates = [];
			renderCandidateViews();
			return;
		}
		try {
			const data = await api(`/api/candidates?job_key=${encodeURIComponent(jobKey)}&top=500`);
			if (generation !== candidateListRequestGeneration || state.activeJob !== jobKey) return;
			state.candidates = data.items || [];
			renderCandidateViews();
		} catch (error) {
			if (generation === candidateListRequestGeneration && state.activeJob === jobKey) {
				toast(error.message, "error");
			}
		}
	};

	openCandidate = async function contextSafeCandidateDetailLoad(id) {
		const generation = ++candidateDetailRequestGeneration;
		const jobKey = state.activeJob;
		try {
			const cached = state.candidateDetails.get(id);
			const detail = cached || await api(`/api/candidates/${encodeURIComponent(id)}`);
			if (generation !== candidateDetailRequestGeneration || state.activeJob !== jobKey) return;
			touchDetailCache(id, detail);
			renderCandidateDrawer(detail);
			const drawer = $("#candidate-drawer");
			drawer.classList.add("open");
			drawer.setAttribute("aria-hidden", "false");
		} catch (error) {
			if (generation === candidateDetailRequestGeneration && state.activeJob === jobKey) {
				toast(error.message, "error");
			}
		}
	};

	editJob = async function contextSafeJobEditorLoad(key) {
		const generation = ++jobEditRequestGeneration;
		try {
			const job = await api(`/api/jobs/${encodeURIComponent(key)}`);
			if (generation !== jobEditRequestGeneration) return;
			openJobEditor(job);
		} catch (error) {
			if (generation === jobEditRequestGeneration) toast(error.message, "error");
		}
	};
})();
