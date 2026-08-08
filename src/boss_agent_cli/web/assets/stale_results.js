/* Make stale scores visible without treating them as current job decisions. */
(() => {
	let staleCount = 0;

	function normalizedStaleCount(value) {
		const parsed = Number(value || 0);
		return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 0;
	}

	function renderNotice(panelName) {
		const panel = document.querySelector(`[data-view-panel="${panelName}"]`);
		if (!panel) return;
		const id = `stale-results-${panelName}`;
		let notice = document.getElementById(id);
		if (!staleCount) {
			notice?.remove();
			return;
		}
		if (!notice) {
			notice = document.createElement('div');
			notice.id = id;
			notice.className = 'stale-results-warning';
			const anchor = panelName === 'dashboard'
				? panel.querySelector('.metrics-grid')
				: panel.querySelector('.filter-toolbar');
			if (anchor) anchor.before(notice);
			else panel.prepend(notice);
		}
		notice.innerHTML = `<div><strong>${staleCount} 位候选人的评分需要重新计算</strong><span>岗位 JD 或评分规则已变化，旧评估已从当前排名、统计和 CSV 中排除；历史记录仍保留用于审计。</span></div><button type="button" class="button secondary compact-button" data-stale-open-screening>去智能筛选</button>`;
	}

	const baseApiForStaleResults = api;
	api = async function staleAwareApi(path, options = {}) {
		const data = await baseApiForStaleResults(path, options);
		if (String(path).startsWith('/api/candidates?')) {
			staleCount = normalizedStaleCount(data?.stale_count);
		}
		return data;
	};

	const baseRenderDashboardForStaleResults = renderDashboard;
	renderDashboard = function renderDashboardWithStaleResults(report, analytics) {
		staleCount = normalizedStaleCount(report?.stale_count ?? analytics?.stale_count ?? staleCount);
		baseRenderDashboardForStaleResults(report, analytics);
		renderNotice('dashboard');
	};

	const baseRenderCandidateViewsForStaleResults = renderCandidateViews;
	renderCandidateViews = function renderCandidateViewsWithStaleResults() {
		baseRenderCandidateViewsForStaleResults();
		renderNotice('pipeline');
	};

	const baseRenderEmptyDashboardForStaleResults = renderEmptyDashboard;
	renderEmptyDashboard = function renderEmptyDashboardWithStaleResults() {
		staleCount = 0;
		baseRenderEmptyDashboardForStaleResults();
		renderNotice('dashboard');
		renderNotice('pipeline');
	};

	document.addEventListener('click', event => {
		if (!event.target.closest('[data-stale-open-screening]')) return;
		setView('screening');
	});
})();
