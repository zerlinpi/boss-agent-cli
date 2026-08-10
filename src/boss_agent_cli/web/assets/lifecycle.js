/* Local data lifecycle and candidate-comparison controls. */
const baseRenderOnboarding = renderOnboarding;
renderOnboarding = function renderOnboardingWithOptionalBossLogin(onboarding) {
	baseRenderOnboarding(onboarding);
	const complete = ["ai_configured", "has_job", "has_candidates"].every(key => Boolean(onboarding[key]));
	$("#onboarding").classList.toggle("hidden", complete);
	const authStep = $('[data-onboarding-key="auth_ready"]');
	if (authStep) {
		authStep.disabled = false;
		authStep.classList.toggle("done", Boolean(onboarding.auth_ready));
		const label = authStep.querySelector("span");
		if (label) label.textContent = onboarding.auth_ready ? "BOSS 已登录" : "可选：登录 BOSS";
	}
};

function injectJobDeleteButtons() {
	$$('.job-card').forEach(card => {
		if (card.querySelector('[data-action="delete-job"]')) return;
		const actions = card.querySelector('.job-actions');
		if (!actions) return;
		const button = document.createElement('button');
		button.className = 'button danger-subtle';
		button.dataset.action = 'delete-job';
		button.dataset.jobKey = card.dataset.jobKey;
		button.textContent = '删除';
		actions.append(button);
	});
}

function injectCompareButton() {
	const toolbar = $("#bulk-toolbar");
	if (!toolbar || toolbar.querySelector('[data-action="compare-candidates"]')) return;
	const button = document.createElement('button');
	button.className = 'button secondary';
	button.dataset.action = 'compare-candidates';
	button.textContent = '对比候选人';
	toolbar.insertBefore(button, $("#bulk-apply"));
}

const baseRenderJobs = renderJobs;
renderJobs = function renderJobsWithLifecycle() {
	baseRenderJobs();
	injectJobDeleteButtons();
};

function injectCandidateFreshness(record, container) {
	const freshness = record?.freshness;
	if (!freshness || freshness.is_current !== false || container.querySelector('.candidate-freshness-warning')) return;
	const section = document.createElement('section');
	section.className = 'detail-section candidate-freshness-warning';
	const latestId = String(freshness.latest_evaluation_id || '');
	const currentId = String(record.id || '');
	const latestAction = latestId && latestId !== currentId
		? `<button type="button" class="button secondary compact-button" data-candidate-id="${escapeHtml(latestId)}">打开最新评估</button>`
		: `<button type="button" class="button secondary compact-button" data-action="show-screening">重新筛选</button>`;
	section.innerHTML = `<div><strong>当前查看的是历史评估</strong><p>${escapeHtml(freshness.reason || '岗位或候选人评估已发生变化，请以最新结果为准。')}</p></div>${latestAction}`;
	const score = container.querySelector('.detail-score');
	if (score) score.after(section);
	else container.prepend(section);
}

const baseRenderCandidateDrawer = renderCandidateDrawer;
renderCandidateDrawer = function renderCandidateDrawerWithLifecycle(record) {
	baseRenderCandidateDrawer(record);
	const container = $("#drawer-content");
	if (!container) return;
	injectCandidateFreshness(record, container);
	if (container.querySelector('[data-action="delete-candidate"]')) return;
	const section = document.createElement('section');
	section.className = 'detail-section danger-zone';
	section.innerHTML = `<div><h3>删除本地数据</h3><p>清理该候选人在当前岗位下的全部历史评估和关联回复草稿。其他岗位中的同一候选人不会被删除。此操作不可撤销。</p></div><button class="button danger-subtle" data-action="delete-candidate" data-evaluation-id="${escapeHtml(record.id)}">永久删除</button>`;
	container.append(section);
};

async function deleteCandidateLocal(evaluationId) {
	if (!window.confirm('确认删除该候选人在当前岗位下的全部本地评估和回复数据？其他岗位数据会保留，此操作不可撤销。')) return;
	try {
		const result = await api(`/api/candidates/${encodeURIComponent(evaluationId)}/status`, {
			method: 'POST', body: JSON.stringify({ status: '__delete__', note: '' }),
		});
		state.candidateDetails.delete(evaluationId);
		state.selectedCandidates.delete(evaluationId);
		closeDrawer();
		toast(`已删除 ${result.evaluation_count} 条评估和 ${result.reply_count} 条草稿`);
		await bootstrap();
	} catch (error) { toast(error.message, 'error'); }
}

async function deleteJobLocal(jobKey) {
	const job = state.jobs.find(item => item.job_key === jobKey);
	if (!window.confirm(`确认删除岗位“${job?.title || jobKey}”及其全部本地候选人数据？此操作不可撤销。`)) return;
	try {
		await api('/api/jobs', { method: 'POST', body: JSON.stringify({ _delete: true, job_key: jobKey }) });
		if (state.activeJob === jobKey) {
			state.activeJob = '';
			localStorage.removeItem('boss-web-active-job');
		}
		toast('岗位及关联本地数据已删除');
		await bootstrap();
	} catch (error) { toast(error.message, 'error'); }
}

function closeCandidateComparison() {
	$("#candidate-compare-modal")?.remove();
}

function compareColumn(record) {
	const evaluation = record.evaluation || {};
	return `<article class="compare-column"><header><strong>${escapeHtml(record.candidate_name || '候选人')}</strong><span class="score">${evaluation.total_score ?? '—'}</span></header><span class="badge ${escapeHtml(evaluation.recommendation)}">${recommendationLabel(evaluation.recommendation)}</span><p class="compare-summary">${escapeHtml(evaluation.summary || '暂无摘要')}</p><section><h4>优势</h4><div class="chip-list">${chips(evaluation.strengths, 'good', '暂无明确优势')}</div></section><section><h4>风险</h4><div class="chip-list">${chips(evaluation.concerns, 'risk', '暂无风险项')}</div></section><section><h4>评分维度</h4><div class="compare-dimensions">${(evaluation.dimensions || []).map(item => `<div><span>${escapeHtml(item.name)}</span><strong>${item.score}/${item.max_score}</strong><i style="--value:${Math.round(Number(item.score || 0) / Math.max(1, Number(item.max_score || 1)) * 100)}%"></i></div>`).join('') || '<small>暂无维度数据</small>'}</div></section></article>`;
}

async function compareSelectedCandidates() {
	const ids = [...state.selectedCandidates];
	if (ids.length < 2 || ids.length > 4) {
		toast('请选择 2–4 位候选人进行对比', 'error');
		return;
	}
	try {
		const records = await Promise.all(ids.map(async id => {
			const cached = state.candidateDetails.get(id);
			if (cached) return cached;
			const detail = await api(`/api/candidates/${encodeURIComponent(id)}`);
			state.candidateDetails.set(id, detail);
			return detail;
		}));
		closeCandidateComparison();
		const modal = document.createElement('aside');
		modal.id = 'candidate-compare-modal';
		modal.className = 'compare-modal';
		modal.innerHTML = `<div class="compare-backdrop" data-action="close-comparison"></div><div class="compare-panel"><header class="compare-header"><div><p class="eyebrow">SIDE-BY-SIDE</p><h2>候选人对比</h2><span>并排查看 AI 证据，最终结论仍由招聘人员决定。</span></div><button class="icon-button" data-action="close-comparison">×</button></header><div class="compare-grid" style="--compare-columns:${records.length}">${records.map(compareColumn).join('')}</div></div>`;
		document.body.append(modal);
	} catch (error) { toast(error.message, 'error'); }
}

document.addEventListener('click', event => {
	const button = event.target.closest('[data-action="delete-job"],[data-action="delete-candidate"],[data-action="compare-candidates"],[data-action="close-comparison"],[data-action="show-screening"]');
	if (!button) return;
	event.preventDefault();
	event.stopPropagation();
	if (button.dataset.action === 'delete-job') deleteJobLocal(button.dataset.jobKey);
	if (button.dataset.action === 'delete-candidate') deleteCandidateLocal(button.dataset.evaluationId);
	if (button.dataset.action === 'compare-candidates') compareSelectedCandidates();
	if (button.dataset.action === 'close-comparison') closeCandidateComparison();
	if (button.dataset.action === 'show-screening') { closeDrawer(); setView('screening'); }
}, true);

document.addEventListener('keydown', event => {
	if (event.key === 'Escape') closeCandidateComparison();
});

injectJobDeleteButtons();
injectCompareButton();
