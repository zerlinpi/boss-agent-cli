/* Local data lifecycle controls layered onto the zero-build recruiter console. */
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

const baseRenderJobs = renderJobs;
renderJobs = function renderJobsWithLifecycle() {
	baseRenderJobs();
	injectJobDeleteButtons();
};

const baseRenderCandidateDrawer = renderCandidateDrawer;
renderCandidateDrawer = function renderCandidateDrawerWithLifecycle(record) {
	baseRenderCandidateDrawer(record);
	const container = $("#drawer-content");
	if (!container || container.querySelector('[data-action="delete-candidate"]')) return;
	const section = document.createElement('section');
	section.className = 'detail-section danger-zone';
	section.innerHTML = `<div><h3>删除本地数据</h3><p>清理该候选人的全部历史评估和关联回复草稿。此操作不可撤销。</p></div><button class="button danger-subtle" data-action="delete-candidate" data-evaluation-id="${escapeHtml(record.id)}">永久删除</button>`;
	container.append(section);
};

async function deleteCandidateLocal(evaluationId) {
	if (!window.confirm('确认删除该候选人的全部本地评估和回复数据？此操作不可撤销。')) return;
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

document.addEventListener('click', event => {
	const button = event.target.closest('[data-action="delete-job"],[data-action="delete-candidate"]');
	if (!button) return;
	event.preventDefault();
	event.stopPropagation();
	if (button.dataset.action === 'delete-job') deleteJobLocal(button.dataset.jobKey);
	if (button.dataset.action === 'delete-candidate') deleteCandidateLocal(button.dataset.evaluationId);
}, true);

injectJobDeleteButtons();
