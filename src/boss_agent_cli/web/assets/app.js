const TOKEN = "__BOSS_WEB_TOKEN__";
const state = {
	bootstrap: null,
	jobs: [],
	activeJob: localStorage.getItem("boss-web-active-job") || "",
	candidates: [],
	candidateDetails: new Map(),
	replies: [],
	audit: [],
	tasks: [],
	selectedFiles: [],
	selectedCandidates: new Set(),
	pipelineMode: localStorage.getItem("boss-web-pipeline-mode") || "table",
	activeTask: null,
	pollTimer: null,
	taskCallbacks: new Map(),
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = (value = "") => String(value)
	.replaceAll("&", "&amp;")
	.replaceAll("<", "&lt;")
	.replaceAll(">", "&gt;")
	.replaceAll('"', "&quot;")
	.replaceAll("'", "&#039;");

async function api(path, options = {}) {
	const response = await fetch(path, {
		...options,
		headers: {
			"Content-Type": "application/json",
			"X-Boss-Web-Token": TOKEN,
			...(options.headers || {}),
		},
	});
	let payload;
	try { payload = await response.json(); }
	catch { throw new Error(`服务器返回无法解析的响应（${response.status}）`); }
	if (!response.ok || !payload.ok) {
		const error = new Error(payload?.error?.message || `请求失败（${response.status}）`);
		error.code = payload?.error?.code || "REQUEST_FAILED";
		throw error;
	}
	return payload.data;
}

function toast(message, type = "success") {
	const node = document.createElement("div");
	node.className = `toast ${type}`;
	node.textContent = message;
	$("#toast-stack").append(node);
	setTimeout(() => node.remove(), 4200);
}

function setView(name) {
	$$('.nav-item').forEach(item => item.classList.toggle("active", item.dataset.view === name));
	$$('[data-view-panel]').forEach(panel => panel.classList.toggle("active", panel.dataset.viewPanel === name));
	const titles = {
		dashboard: "招聘概览", jobs: "岗位配置", screening: "智能筛选",
		pipeline: "候选人工作台", replies: "回复草稿", activity: "任务与审计", settings: "系统设置",
	};
	$("#page-title").textContent = titles[name] || "招聘控制台";
	$("#sidebar").classList.remove("open");
	if (name === "dashboard") loadDashboard();
	if (name === "pipeline") loadCandidates();
	if (name === "replies") loadReplies();
	if (name === "activity") loadActivity();
}

function activeJobRecord() {
	return state.jobs.find(job => job.job_key === state.activeJob) || null;
}

async function bootstrap() {
	try {
		state.bootstrap = await api("/api/bootstrap");
		state.jobs = state.bootstrap.jobs || [];
		state.tasks = state.bootstrap.tasks || [];
		if (!state.activeJob || !state.jobs.some(job => job.job_key === state.activeJob)) {
			state.activeJob = state.jobs[0]?.job_key || "";
		}
		applyBootstrap();
		await Promise.all([loadDashboard(), loadReplies(), loadActivity()]);
		const running = state.tasks.find(task => ["queued", "running"].includes(task.status));
		if (running) watchTask(running.id);
	} catch (error) {
		toast(error.message, "error");
	}
}

function applyBootstrap() {
	const data = state.bootstrap;
	const auth = data.auth || {};
	const ai = data.ai || {};
	const mode = data.operating_mode || "assisted";
	$("#sidebar-auth-dot").className = `status-dot ${auth.logged_in ? "online" : "warn"}`;
	$("#sidebar-auth-text").textContent = auth.logged_in ? "BOSS 已登录" : "BOSS 未登录";
	$("#sidebar-mode-text").textContent = `${mode === "research" ? "Research" : "Assisted"} Mode`;
	$("#system-ai").textContent = ai.configured ? `${ai.provider} / ${ai.model}` : "未配置";
	$("#system-auth").textContent = auth.logged_in ? "已登录" : "未登录";
	$("#system-mode").textContent = mode === "research" ? "Research" : "Assisted";
	$("#system-data").textContent = data.data_dir || "—";
	$("#auth-description").textContent = auth.summary || "检查本地登录状态";
	setBadge($("#auth-badge"), auth.logged_in ? "已登录" : "未登录", auth.logged_in ? "interview" : "manual_review");
	setBadge($("#ai-config-badge"), ai.configured ? "已配置" : "未配置", ai.configured ? "interview" : "manual_review");
	setBadge($("#mode-badge"), mode, mode === "research" ? "manual_review" : "new");
	const radio = $(`input[name="operating_mode"][value="${mode}"]`);
	if (radio) radio.checked = true;
	populateProviders(ai);
	populateJobSelectors();
	populateStatusControls();
	renderJobs();
	renderOnboarding(data.onboarding || {});
	renderTaskHistory();
}

function renderOnboarding(onboarding) {
	const complete = Object.values(onboarding).every(Boolean);
	$("#onboarding").classList.toggle("hidden", complete);
	$$('[data-onboarding-key]').forEach(button => {
		const done = Boolean(onboarding[button.dataset.onboardingKey]);
		button.classList.toggle("done", done);
		button.disabled = done;
	});
}

function populateProviders(ai) {
	const select = $("#ai-provider");
	const providers = Object.keys(ai.providers || {});
	select.innerHTML = providers.map(provider => `<option value="${escapeHtml(provider)}">${escapeHtml(provider)}</option>`).join("");
	select.value = ai.provider || providers[0] || "custom";
	$("#ai-model").value = ai.model || "";
	$("#ai-base-url").value = ai.base_url || "";
	$("#ai-temperature").value = ai.temperature ?? 0.2;
	$("#ai-max-tokens").value = ai.max_tokens ?? 4096;
}

function populateJobSelectors() {
	const select = $("#global-job-select");
	if (!state.jobs.length) {
		select.innerHTML = '<option value="">请先创建岗位</option>';
		select.disabled = true;
		return;
	}
	select.disabled = false;
	select.innerHTML = state.jobs.map(job => `<option value="${escapeHtml(job.job_key)}">${escapeHtml(job.title || job.job_key)}</option>`).join("");
	select.value = state.activeJob;
	const active = activeJobRecord();
	if (active?.boss_job_id) $("#boss-job-id").value = active.boss_job_id;
}

function populateStatusControls() {
	const statuses = state.bootstrap?.candidate_statuses || [];
	const filter = $("#candidate-status-filter");
	const current = filter.value;
	filter.innerHTML = '<option value="">全部状态</option>' + statuses.map(status => `<option value="${status}">${statusLabel(status)}</option>`).join("");
	filter.value = current;
	const bulk = $("#bulk-status");
	bulk.innerHTML = '<option value="">选择目标阶段</option>' + statuses.map(status => `<option value="${status}">${statusLabel(status)}</option>`).join("");
}

async function loadDashboard() {
	if (!state.activeJob) {
		renderEmptyDashboard();
		return;
	}
	try {
		const data = await api(`/api/candidates?job_key=${encodeURIComponent(state.activeJob)}&top=500`);
		state.candidates = data.items || [];
		renderDashboard(data.report || {}, data.analytics || {});
		renderCandidateViews();
	} catch (error) {
		toast(error.message, "error");
	}
}

function renderEmptyDashboard() {
	["#metric-total", "#metric-interview", "#metric-average"].forEach(id => $(id).textContent = "0");
	$("#metric-conversion").textContent = "0%";
	$("#dashboard-candidates").className = "candidate-stack empty-state";
	$("#dashboard-candidates").textContent = "请先创建岗位并执行筛选";
	$("#funnel-list").innerHTML = "";
	$("#score-distribution").innerHTML = "";
	state.candidates = [];
	renderCandidateViews();
}

function renderDashboard(report, analytics) {
	const rec = report.recommendation_counts || {};
	const statuses = report.status_counts || {};
	$("#metric-total").textContent = report.total_candidates || 0;
	$("#metric-interview").textContent = (rec.strong_interview || 0) + (rec.interview || 0);
	$("#metric-average").textContent = analytics.average_score || 0;
	$("#metric-conversion").textContent = `${analytics.interview_conversion || 0}%`;
	$("#system-recent").textContent = analytics.recent_7d || 0;

	const top = (report.top_candidates || []).slice(0, 6);
	const container = $("#dashboard-candidates");
	if (!top.length) {
		container.className = "candidate-stack empty-state";
		container.textContent = "当前岗位暂无评估结果";
	} else {
		container.className = "candidate-stack";
		container.innerHTML = top.map(candidate => `<button class="candidate-row" data-candidate-id="${escapeHtml(candidate.evaluation_id)}"><span class="rank-pill">${candidate.rank}</span><span class="candidate-main"><strong>${escapeHtml(candidate.candidate_name || "候选人")}</strong><span>${escapeHtml(candidate.summary || "等待人工复核")}</span></span><span class="score">${candidate.total_score ?? "—"}</span><span class="badge ${escapeHtml(candidate.recommendation)}">${recommendationLabel(candidate.recommendation)}</span></button>`).join("");
	}

	const funnel = [["new", statuses.new || 0], ["shortlisted", statuses.shortlisted || 0], ["interview", statuses.interview || 0], ["hired", statuses.hired || 0], ["rejected", statuses.rejected || 0]];
	const maximum = Math.max(1, ...funnel.map(([, count]) => count));
	$("#funnel-list").innerHTML = funnel.map(([name, count]) => `<div class="funnel-item"><span>${statusLabel(name)}</span><div class="funnel-bar"><i style="--value:${Math.round(count / maximum * 100)}%"></i></div><strong>${count}</strong></div>`).join("");

	const distribution = analytics.score_distribution || {};
	const maxDistribution = Math.max(1, ...Object.values(distribution));
	$("#score-distribution").innerHTML = Object.entries(distribution).map(([range, count]) => `<div class="distribution-item"><div><span>${range} 分</span><strong>${count}</strong></div><div class="distribution-bar"><i style="--value:${Math.round(count / maxDistribution * 100)}%"></i></div></div>`).join("") || '<div class="empty-state small">暂无评分数据</div>';
}

function renderJobs() {
	const grid = $("#job-grid");
	if (!state.jobs.length) {
		grid.innerHTML = '<div class="panel empty-state">尚未创建岗位。点击“新建岗位”开始配置。</div>';
		return;
	}
	grid.innerHTML = state.jobs.map(job => `<article class="job-card ${job.job_key === state.activeJob ? "active" : ""}" data-job-key="${escapeHtml(job.job_key)}"><header><div><span class="job-key">${escapeHtml(job.job_key)}</span><h3>${escapeHtml(job.title || job.job_key)}</h3></div><span class="badge ${job.boss_job_id ? "interview" : "manual_review"}">${job.boss_job_id ? "BOSS 已关联" : "未关联 BOSS"}</span></header><div class="job-meta"><div><span>BOSS 职位 ID</span><strong>${escapeHtml(job.boss_job_id || "—")}</strong></div><div><span>更新时间</span><strong>${formatDate(job.updated_at)}</strong></div></div><div class="job-actions"><button class="button ghost" data-action="select-job" data-job-key="${escapeHtml(job.job_key)}">设为当前</button><button class="button ghost" data-action="edit-job" data-job-key="${escapeHtml(job.job_key)}">编辑</button></div></article>`).join("");
}

function openJobEditor(job = null) {
	const editor = $("#job-editor");
	const form = $("#job-form");
	form.reset();
	$("#job-analysis").classList.add("hidden");
	$("#job-analysis").innerHTML = "";
	$("#job-editor-title").textContent = job ? "编辑岗位" : "新建岗位";
	if (job) {
		form.elements.job_key.value = job.job_key || "";
		form.elements.job_key.readOnly = true;
		form.elements.title.value = job.metadata?.title || job.job_key || "";
		form.elements.boss_job_id.value = job.metadata?.boss_job_id || "";
		form.elements.jd_text.value = job.jd_text || "";
		form.elements.rubric.value = JSON.stringify(job.rubric || {}, null, 2);
	} else {
		form.elements.job_key.readOnly = false;
		form.elements.rubric.value = "";
	}
	editor.classList.remove("hidden");
	editor.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function saveJob(event) {
	event.preventDefault();
	const form = event.currentTarget;
	let rubric = null;
	if (form.elements.rubric.value.trim()) {
		try { rubric = JSON.parse(form.elements.rubric.value); }
		catch { toast("评分规则不是有效 JSON", "error"); return; }
	}
	try {
		const job = await api("/api/jobs", { method: "POST", body: JSON.stringify({
			job_key: form.elements.job_key.value,
			title: form.elements.title.value,
			boss_job_id: form.elements.boss_job_id.value,
			jd_text: form.elements.jd_text.value,
			rubric,
		}) });
		state.activeJob = job.job_key;
		localStorage.setItem("boss-web-active-job", state.activeJob);
		$("#job-editor").classList.add("hidden");
		toast("岗位配置已保存");
		await bootstrap();
	} catch (error) { toast(error.message, "error"); }
}

async function analyzeJob() {
	const form = $("#job-form");
	const jdText = form.elements.jd_text.value.trim();
	if (jdText.length < 30) { toast("请先填写完整岗位 JD", "error"); return; }
	try {
		const task = await api("/api/jobs/analyze", { method: "POST", body: JSON.stringify({ jd_text: jdText }) });
		state.taskCallbacks.set(task.id, result => {
			if (result.title && !form.elements.title.value.trim()) form.elements.title.value = result.title;
			form.elements.rubric.value = JSON.stringify(result.rubric || {}, null, 2);
			const panel = $("#job-analysis");
			panel.classList.remove("hidden");
			panel.innerHTML = `<strong>岗位画像</strong><p>${escapeHtml(result.persona_summary || "已生成评分规则")}</p>${Array.isArray(result.suggested_questions) && result.suggested_questions.length ? `<div class="chip-list">${result.suggested_questions.map(item => `<span class="chip">${escapeHtml(item)}</span>`).join("")}</div>` : ""}`;
		});
		watchTask(task.id);
		toast("岗位分析任务已启动");
	} catch (error) { toast(error.message, "error"); }
}

async function editJob(key) {
	try { openJobEditor(await api(`/api/jobs/${encodeURIComponent(key)}`)); }
	catch (error) { toast(error.message, "error"); }
}

function selectJob(key) {
	state.activeJob = key;
	localStorage.setItem("boss-web-active-job", key);
	$("#global-job-select").value = key;
	const job = activeJobRecord();
	$("#boss-job-id").value = job?.boss_job_id || "";
	state.selectedCandidates.clear();
	renderJobs();
	loadDashboard();
}

async function fileToDocument(file) {
	if (file.name.toLowerCase().endsWith(".json")) {
		try { return { name: file.name, payload: JSON.parse(await file.text()) }; }
		catch { /* send raw so the server returns a file-specific parse error */ }
	}
	const bytes = new Uint8Array(await file.arrayBuffer());
	let binary = "";
	const chunk = 0x8000;
	for (let index = 0; index < bytes.length; index += chunk) {
		binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
	}
	return { name: file.name, content_base64: btoa(binary), mime_type: file.type || "application/octet-stream" };
}

function updateFileSelection(files) {
	const allowed = [".json", ".txt", ".md", ".pdf", ".docx"];
	const accepted = [...files].filter(file => allowed.some(extension => file.name.toLowerCase().endsWith(extension)) && file.size <= 12 * 1024 * 1024).slice(0, 100);
	let total = 0;
	state.selectedFiles = accepted.filter(file => {
		if (total + file.size > 45 * 1024 * 1024) return false;
		total += file.size;
		return true;
	});
	$("#resume-file-summary").textContent = state.selectedFiles.length ? `已选择 ${state.selectedFiles.length} 个文件` : "尚未选择文件";
	$("#resume-file-list").innerHTML = state.selectedFiles.slice(0, 8).map(file => `<span class="file-chip">${escapeHtml(file.name)} <small>${formatBytes(file.size)}</small></span>`).join("") + (state.selectedFiles.length > 8 ? `<span class="file-chip">另有 ${state.selectedFiles.length - 8} 份</span>` : "");
}

async function screenLocal() {
	if (!state.activeJob) { toast("请先创建并选择岗位", "error"); return; }
	if (!state.selectedFiles.length) { toast("请选择至少一份简历", "error"); return; }
	const button = $("#screen-local-button");
	button.disabled = true;
	button.textContent = "正在读取文件…";
	try {
		const documents = await Promise.all(state.selectedFiles.map(fileToDocument));
		const task = await api("/api/screen/local", { method: "POST", body: JSON.stringify({ job_key: state.activeJob, documents, force: $("#local-force").checked }) });
		watchTask(task.id);
		toast("本地简历筛选任务已启动");
	} catch (error) { toast(`读取简历失败：${error.message}`, "error"); }
	finally { button.disabled = false; button.textContent = "开始本地筛选"; }
}

async function screenBoss() {
	if (!state.activeJob) { toast("请先创建并选择岗位", "error"); return; }
	const jobId = $("#boss-job-id").value.trim();
	if (!jobId) { toast("请填写 BOSS 职位 ID", "error"); return; }
	try {
		const task = await api("/api/screen/boss", { method: "POST", body: JSON.stringify({
			job_key: state.activeJob,
			job_id: jobId,
			pages: Number($("#boss-pages").value),
			limit: Number($("#boss-limit").value),
			draft_top: Number($("#boss-draft-top").value),
			include_chat: $("#boss-include-chat").checked,
			force: $("#boss-force").checked,
		}) });
		watchTask(task.id);
		toast("BOSS 候选人筛选任务已启动");
	} catch (error) { toast(error.message, "error"); }
}

function watchTask(id) {
	state.activeTask = id;
	clearInterval(state.pollTimer);
	$("#task-banner").classList.remove("hidden");
	const poll = async () => {
		try {
			const task = await api(`/api/tasks/${encodeURIComponent(id)}`);
			renderTask(task);
			if (["completed", "failed"].includes(task.status)) {
				clearInterval(state.pollTimer);
				state.pollTimer = null;
				state.activeTask = null;
				if (task.status === "completed") {
					const callback = state.taskCallbacks.get(id);
					if (callback) callback(task.result || {});
					state.taskCallbacks.delete(id);
					if (["screen-local", "screen-boss"].includes(task.kind)) renderScreenResult(task.result || {});
					toast("任务执行完成");
					await bootstrap();
				} else {
					toast(task.error?.message || "任务执行失败", "error");
				}
				setTimeout(() => $("#task-banner").classList.add("hidden"), 2500);
			}
		} catch (error) {
			clearInterval(state.pollTimer);
			toast(error.message, "error");
		}
	};
	poll();
	state.pollTimer = setInterval(poll, 1000);
}

function renderTask(task) {
	$("#task-title").textContent = task.metadata?.title || taskKindLabel(task.kind);
	$("#task-message").textContent = task.message || task.status;
	$("#task-progress").style.setProperty("--value", `${task.progress || 0}%`);
	$("#task-percent").textContent = `${task.progress || 0}%`;
}

function renderScreenResult(result) {
	const container = $("#screen-result");
	const errors = result.failed || [];
	container.className = "";
	container.innerHTML = `<div class="result-summary"><div><span>发现候选人</span><strong>${result.discovered_count ?? result.processed_count ?? 0}</strong></div><div><span>完成评估</span><strong>${result.processed_count || 0}</strong></div><div><span>跳过未变化</span><strong>${result.skipped_unchanged_count || 0}</strong></div><div><span>回复草稿</span><strong>${result.reply_drafts?.length || 0}</strong></div></div>${errors.length ? `<div class="result-errors"><strong>${errors.length} 项未成功：</strong><br>${errors.slice(0, 8).map(item => escapeHtml(item.error || "未知错误")).join("<br>")}</div>` : ""}`;
}

async function loadCandidates() {
	if (!state.activeJob) { state.candidates = []; renderCandidateViews(); return; }
	try {
		const data = await api(`/api/candidates?job_key=${encodeURIComponent(state.activeJob)}&top=500`);
		state.candidates = data.items || [];
		renderCandidateViews();
	} catch (error) { toast(error.message, "error"); }
}

function filteredCandidates() {
	const term = $("#candidate-search").value.trim().toLowerCase();
	const status = $("#candidate-status-filter").value;
	const recommendation = $("#candidate-recommendation-filter").value;
	const sort = $("#candidate-sort").value;
	const items = state.candidates.filter(candidate => {
		if (status && candidate.status !== status) return false;
		if (recommendation && candidate.recommendation !== recommendation) return false;
		if (!term) return true;
		return [candidate.candidate_name, candidate.summary, ...(candidate.strengths || []), ...(candidate.concerns || [])].join(" ").toLowerCase().includes(term);
	});
	items.sort((a, b) => {
		if (sort === "score-asc") return Number(a.total_score || 0) - Number(b.total_score || 0);
		if (sort === "name") return String(a.candidate_name || "").localeCompare(String(b.candidate_name || ""), "zh-CN");
		return Number(b.total_score || 0) - Number(a.total_score || 0);
	});
	return items;
}

function renderCandidateViews() {
	renderCandidateTable();
	renderKanban();
	applyPipelineMode();
	updateBulkToolbar();
}

function renderCandidateTable() {
	const items = filteredCandidates();
	const body = $("#candidate-table-body");
	$("#candidate-empty").classList.toggle("hidden", items.length > 0);
	body.innerHTML = items.map(candidate => `<tr><td><input type="checkbox" data-select-candidate="${escapeHtml(candidate.evaluation_id)}" ${state.selectedCandidates.has(candidate.evaluation_id) ? "checked" : ""}></td><td><span class="rank-pill">${candidate.rank}</span></td><td class="table-candidate"><strong>${escapeHtml(candidate.candidate_name || "候选人")}</strong><span>${escapeHtml((candidate.strengths || []).slice(0, 2).join(" · ") || "暂无优势摘要")}</span></td><td><span class="score">${candidate.total_score ?? "—"}</span></td><td><span class="badge ${escapeHtml(candidate.recommendation)}">${recommendationLabel(candidate.recommendation)}</span></td><td><span class="badge ${escapeHtml(candidate.status)}">${statusLabel(candidate.status)}</span></td><td class="table-summary">${escapeHtml(candidate.summary || (candidate.concerns || [])[0] || "待人工复核")}</td><td><button class="button ghost compact-button" data-candidate-id="${escapeHtml(candidate.evaluation_id)}">详情</button></td></tr>`).join("");
	const visibleIds = items.map(item => item.evaluation_id);
	$("#select-all-candidates").checked = visibleIds.length > 0 && visibleIds.every(id => state.selectedCandidates.has(id));
}

function renderKanban() {
	const statuses = state.bootstrap?.candidate_statuses || [];
	const items = filteredCandidates();
	$("#pipeline-kanban").innerHTML = statuses.map(status => {
		const candidates = items.filter(candidate => candidate.status === status);
		return `<section class="kanban-column" data-drop-status="${status}"><header><span>${statusLabel(status)}</span><strong>${candidates.length}</strong></header><div class="kanban-list">${candidates.map(candidate => `<article class="kanban-card" draggable="true" data-drag-candidate="${escapeHtml(candidate.evaluation_id)}" data-candidate-id="${escapeHtml(candidate.evaluation_id)}"><div class="kanban-card-head"><strong>${escapeHtml(candidate.candidate_name || "候选人")}</strong><span class="score">${candidate.total_score ?? "—"}</span></div><span class="badge ${escapeHtml(candidate.recommendation)}">${recommendationLabel(candidate.recommendation)}</span><p>${escapeHtml(candidate.summary || "等待人工复核")}</p><div class="kanban-tags">${(candidate.strengths || []).slice(0, 2).map(item => `<span>${escapeHtml(item)}</span>`).join("")}</div></article>`).join("") || '<div class="kanban-empty">拖放候选人到这里</div>'}</div></section>`;
	}).join("");
}

function setPipelineMode(mode) {
	state.pipelineMode = mode;
	localStorage.setItem("boss-web-pipeline-mode", mode);
	applyPipelineMode();
}

function applyPipelineMode() {
	$("#pipeline-table").classList.toggle("hidden", state.pipelineMode !== "table");
	$("#pipeline-kanban").classList.toggle("hidden", state.pipelineMode !== "kanban");
	$$('[data-pipeline-mode]').forEach(button => button.classList.toggle("active", button.dataset.pipelineMode === state.pipelineMode));
}

function toggleCandidateSelection(id, selected) {
	if (selected) state.selectedCandidates.add(id); else state.selectedCandidates.delete(id);
	updateBulkToolbar();
}

function updateBulkToolbar() {
	$("#bulk-count").textContent = state.selectedCandidates.size;
	$("#bulk-toolbar").classList.toggle("hidden", state.selectedCandidates.size === 0);
}

async function bulkUpdateCandidates() {
	const status = $("#bulk-status").value;
	if (!status) { toast("请选择目标阶段", "error"); return; }
	try {
		const result = await api("/api/candidates/bulk-status", { method: "POST", body: JSON.stringify({ evaluation_ids: [...state.selectedCandidates], status, note: $("#bulk-note").value }) });
		state.selectedCandidates.clear();
		toast(`已更新 ${result.updated_ids.length} 位候选人`);
		await loadDashboard();
	} catch (error) { toast(error.message, "error"); }
}

async function moveCandidate(id, status) {
	try {
		await api(`/api/candidates/${encodeURIComponent(id)}/status`, { method: "POST", body: JSON.stringify({ status, note: "Kanban 拖拽更新" }) });
		state.candidateDetails.delete(id);
		toast(`候选人已移动到“${statusLabel(status)}”`);
		await loadDashboard();
	} catch (error) { toast(error.message, "error"); }
}

async function exportCandidates() {
	if (!state.activeJob) { toast("请先选择岗位", "error"); return; }
	try {
		const data = await api(`/api/export/candidates?job_key=${encodeURIComponent(state.activeJob)}`);
		const blob = new Blob([data.content], { type: "text/csv;charset=utf-8" });
		const url = URL.createObjectURL(blob);
		const link = document.createElement("a");
		link.href = url;
		link.download = data.filename;
		link.click();
		URL.revokeObjectURL(url);
		toast("候选人 CSV 已导出");
	} catch (error) { toast(error.message, "error"); }
}

async function openCandidate(id) {
	try {
		const detail = state.candidateDetails.get(id) || await api(`/api/candidates/${encodeURIComponent(id)}`);
		state.candidateDetails.set(id, detail);
		renderCandidateDrawer(detail);
		const drawer = $("#candidate-drawer");
		drawer.classList.add("open");
		drawer.setAttribute("aria-hidden", "false");
	} catch (error) { toast(error.message, "error"); }
}

function renderCandidateDrawer(record) {
	const evaluation = record.evaluation || {};
	$("#drawer-name").textContent = record.candidate_name || "候选人";
	$("#drawer-content").innerHTML = `<div class="detail-score"><div><span>岗位匹配分</span><strong>${evaluation.total_score ?? "—"}</strong></div><span class="badge ${escapeHtml(evaluation.recommendation)}">${recommendationLabel(evaluation.recommendation)}</span></div><section class="detail-section"><h3>AI 摘要</h3><p>${escapeHtml(evaluation.summary || "暂无摘要")}</p></section><section class="detail-section"><h3>优势</h3><div class="chip-list">${chips(evaluation.strengths, "good", "暂无明确优势")}</div></section><section class="detail-section"><h3>风险与待确认项</h3><div class="chip-list">${chips(evaluation.concerns, "risk", "暂无风险项")}</div></section><section class="detail-section"><h3>建议追问</h3><div class="chip-list">${chips(evaluation.next_questions, "", "暂无追问")}</div></section><section class="detail-section"><h3>评分维度</h3><div class="dimension-list">${(evaluation.dimensions || []).map(item => `<div class="dimension-item"><div class="dimension-head"><span>${escapeHtml(item.name)}</span><strong>${item.score}/${item.max_score}</strong></div><div class="mini-progress"><i style="--value:${Math.round(Number(item.score || 0) / Math.max(1, Number(item.max_score || 1)) * 100)}%"></i></div><p>${escapeHtml(item.reason || "")}</p></div>`).join("") || "暂无评分明细"}</div></section><section class="detail-section"><h3>人工状态</h3><div class="status-editor"><label><span>阶段</span><select id="drawer-status">${(state.bootstrap?.candidate_statuses || []).map(status => `<option value="${status}" ${record.status === status ? "selected" : ""}>${statusLabel(status)}</option>`).join("")}</select></label><label><span>备注</span><input id="drawer-status-note" value="${escapeHtml(record.status_note || "")}" placeholder="记录人工判断"></label><button class="button primary" data-action="save-status" data-evaluation-id="${escapeHtml(record.id)}">保存</button></div></section><section class="detail-section reply-editor"><h3>生成回复草稿</h3><label><span>聊天上下文（可选）</span><textarea id="drawer-conversation" rows="5" placeholder="粘贴候选人的最近消息"></textarea></label><label><span>回复意图</span><select id="drawer-intent"><option value="auto">自动选择</option><option value="ask_followup">追问信息</option><option value="invite_interview">邀请面试</option><option value="clarify">澄清信息</option><option value="decline_draft">婉拒草稿</option><option value="acknowledge">确认收到</option></select></label><button class="button primary" data-action="generate-reply" data-evaluation-id="${escapeHtml(record.id)}">生成草稿</button><div id="drawer-reply-output"></div></section>`;
}

async function saveCandidateStatus(id) {
	try {
		await api(`/api/candidates/${encodeURIComponent(id)}/status`, { method: "POST", body: JSON.stringify({ status: $("#drawer-status").value, note: $("#drawer-status-note").value }) });
		state.candidateDetails.delete(id);
		toast("候选人阶段已更新");
		await loadDashboard();
	} catch (error) { toast(error.message, "error"); }
}

async function generateReply(id) {
	const button = $(`[data-action="generate-reply"][data-evaluation-id="${CSS.escape(id)}"]`);
	button.disabled = true;
	button.textContent = "生成中…";
	try {
		const record = await api("/api/replies", { method: "POST", body: JSON.stringify({ evaluation_id: id, conversation: $("#drawer-conversation").value, intent: $("#drawer-intent").value }) });
		const reply = record.draft?.reply || "";
		$("#drawer-reply-output").innerHTML = `<div class="reply-output">${escapeHtml(reply)}</div><button class="button ghost" data-copy-text="${escapeHtml(reply)}">复制草稿</button>`;
		toast("回复草稿已生成");
		loadReplies();
	} catch (error) { toast(error.message, "error"); }
	finally { button.disabled = false; button.textContent = "生成草稿"; }
}

async function loadReplies() {
	try {
		const data = await api("/api/replies?limit=100");
		state.replies = data.items || [];
		renderReplies();
	} catch (error) { toast(error.message, "error"); }
}

function renderReplies() {
	const grid = $("#reply-grid");
	if (!state.replies.length) { grid.innerHTML = '<div class="panel empty-state">尚未生成回复草稿</div>'; return; }
	grid.innerHTML = state.replies.map(record => {
		const reply = record.draft?.reply || "";
		return `<article class="reply-card"><header><div><span class="badge ${escapeHtml(record.intent)}">${intentLabel(record.intent)}</span><h3>${escapeHtml(record.evaluation_id)}</h3></div><time>${formatDate(record.created_at)}</time></header><div class="reply-text">${escapeHtml(reply)}</div><div class="reply-actions"><small>需要人工审核 · 未自动发送</small><button class="button ghost" data-copy-text="${escapeHtml(reply)}">复制</button></div></article>`;
	}).join("");
}

async function loadActivity() {
	try {
		const [tasks, audit] = await Promise.all([api("/api/tasks?limit=100"), api("/api/audit?limit=100")]);
		state.tasks = tasks.items || [];
		state.audit = audit.items || [];
		renderTaskHistory();
		renderAudit();
	} catch (error) { toast(error.message, "error"); }
}

function renderTaskHistory() {
	const container = $("#task-history");
	if (!container) return;
	if (!state.tasks.length) { container.innerHTML = '<div class="empty-state small">尚无任务记录</div>'; return; }
	container.innerHTML = state.tasks.map(task => `<button class="task-item" data-task-id="${escapeHtml(task.id)}"><div class="task-status ${escapeHtml(task.status)}">${task.status === "completed" ? "✓" : task.status === "failed" ? "!" : "…"}</div><div><strong>${escapeHtml(task.metadata?.title || taskKindLabel(task.kind))}</strong><span>${escapeHtml(task.message || task.status)}</span><small>${formatDate(task.updated_at)}</small></div><span class="task-percent">${task.progress || 0}%</span></button>`).join("");
}

function renderAudit() {
	const container = $("#audit-history");
	const dashboard = $("#dashboard-activity");
	const html = state.audit.map(item => `<article class="activity-item"><span class="activity-dot"></span><div><strong>${escapeHtml(item.summary || item.action)}</strong><small>${formatDate(item.created_at)} · ${escapeHtml(item.action)}</small></div></article>`).join("") || '<div class="empty-state small">尚无操作记录</div>';
	container.innerHTML = html;
	dashboard.innerHTML = state.audit.slice(0, 5).map(item => `<article class="activity-item"><span class="activity-dot"></span><div><strong>${escapeHtml(item.summary || item.action)}</strong><small>${formatDate(item.created_at)}</small></div></article>`).join("") || '<div class="empty-state small">尚无操作记录</div>';
}

async function saveAiSettings(event) {
	event.preventDefault();
	const form = event.currentTarget;
	try {
		await api("/api/settings/ai", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form))) });
		form.elements.api_key.value = "";
		toast("AI 配置已保存");
		await bootstrap();
	} catch (error) { toast(error.message, "error"); }
}

async function setMode(mode) {
	if (mode === "research" && !window.confirm("Research Mode 会读取候选人个人数据。请确认已获得授权，并会在出现验证码或风控提示时立即停止。")) {
		const current = state.bootstrap?.operating_mode || "assisted";
		$(`input[name="operating_mode"][value="${current}"]`).checked = true;
		return;
	}
	try {
		await api("/api/settings/mode", { method: "POST", body: JSON.stringify({ mode }) });
		toast(`运行模式已切换为 ${mode}`);
		await bootstrap();
	} catch (error) { toast(error.message, "error"); }
}

async function loginBoss() {
	try {
		const task = await api("/api/auth/login", { method: "POST", body: JSON.stringify({ timeout: Number($("#login-timeout").value), cookie_source: $("#cookie-source").value, force_cdp: $("#force-cdp").checked }) });
		watchTask(task.id);
		toast("登录流程已启动，请在浏览器窗口中操作");
	} catch (error) { toast(error.message, "error"); }
}

function recommendationLabel(value) {
	return ({ strong_interview: "强烈建议面试", interview: "建议面试", manual_review: "人工复核", not_recommended: "暂不推荐" })[value] || value || "未分类";
}
function statusLabel(value) { return ({ new: "新候选人", shortlisted: "已入围", interview: "面试中", hold: "待定", rejected: "不合适", hired: "已录用" })[value] || value || "未知"; }
function intentLabel(value) { return ({ acknowledge: "确认收到", ask_followup: "追问", invite_interview: "面试邀请", clarify: "澄清", decline_draft: "婉拒" })[value] || value || "草稿"; }
function taskKindLabel(value) { return ({ login: "BOSS 登录", "screen-local": "本地简历筛选", "screen-boss": "BOSS 候选人筛选", "analyze-job": "AI 岗位分析" })[value] || value || "后台任务"; }
function setBadge(node, text, className = "") { node.textContent = text; node.className = `badge ${className}`; }
function formatDate(value) { if (!value) return "—"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }); }
function formatBytes(value) { if (value < 1024) return `${value} B`; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 / 1024).toFixed(1)} MB`; }
function chips(items, className, empty) { return Array.isArray(items) && items.length ? items.map(item => `<span class="chip ${className}">${escapeHtml(item)}</span>`).join("") : `<span class="chip">${empty}</span>`; }
function closeDrawer() { const drawer = $("#candidate-drawer"); drawer.classList.remove("open"); drawer.setAttribute("aria-hidden", "true"); }

function bindEvents() {
	$$('.nav-item').forEach(button => button.addEventListener("click", () => setView(button.dataset.view)));
	$("#mobile-menu").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
	$("#global-job-select").addEventListener("change", event => selectJob(event.target.value));
	$("#refresh-button").addEventListener("click", bootstrap);
	$$('[data-action="open-screening"]').forEach(button => button.addEventListener("click", () => setView("screening")));
	$$('[data-onboarding-view]').forEach(button => button.addEventListener("click", () => setView(button.dataset.onboardingView)));
	$("#new-job-button").addEventListener("click", () => openJobEditor());
	$("#job-form").addEventListener("submit", saveJob);
	$("#analyze-jd-button").addEventListener("click", analyzeJob);
	$("#resume-files").addEventListener("change", event => updateFileSelection(event.target.files));
	const drop = $("#resume-drop");
	["dragenter", "dragover"].forEach(name => drop.addEventListener(name, event => { event.preventDefault(); drop.classList.add("dragging"); }));
	["dragleave", "drop"].forEach(name => drop.addEventListener(name, event => { event.preventDefault(); drop.classList.remove("dragging"); }));
	drop.addEventListener("drop", event => updateFileSelection(event.dataTransfer.files));
	$("#screen-local-button").addEventListener("click", screenLocal);
	$("#screen-boss-button").addEventListener("click", screenBoss);
	["#candidate-search", "#candidate-status-filter", "#candidate-recommendation-filter", "#candidate-sort"].forEach(selector => $(selector).addEventListener(selector === "#candidate-search" ? "input" : "change", renderCandidateViews));
	$$('[data-pipeline-mode]').forEach(button => button.addEventListener("click", () => setPipelineMode(button.dataset.pipelineMode)));
	$("#select-all-candidates").addEventListener("change", event => { filteredCandidates().forEach(candidate => toggleCandidateSelection(candidate.evaluation_id, event.target.checked)); renderCandidateTable(); });
	$("#bulk-apply").addEventListener("click", bulkUpdateCandidates);
	$("#bulk-clear").addEventListener("click", () => { state.selectedCandidates.clear(); renderCandidateViews(); });
	$("#export-button").addEventListener("click", exportCandidates);
	$("#ai-form").addEventListener("submit", saveAiSettings);
	$("#ai-provider").addEventListener("change", event => { $("#ai-base-url").value = state.bootstrap?.ai?.providers?.[event.target.value] || ""; });
	$("#login-button").addEventListener("click", loginBoss);
	$$('input[name="operating_mode"]').forEach(radio => radio.addEventListener("change", () => setMode(radio.value)));
	$("#activity-refresh").addEventListener("click", loadActivity);

	document.addEventListener("change", event => {
		const checkbox = event.target.closest('[data-select-candidate]');
		if (checkbox) toggleCandidateSelection(checkbox.dataset.selectCandidate, checkbox.checked);
	});
	document.addEventListener("dragstart", event => {
		const card = event.target.closest('[data-drag-candidate]');
		if (card) event.dataTransfer.setData("text/plain", card.dataset.dragCandidate);
	});
	document.addEventListener("dragover", event => {
		const column = event.target.closest('[data-drop-status]');
		if (column) { event.preventDefault(); column.classList.add("drag-over"); }
	});
	document.addEventListener("dragleave", event => event.target.closest('[data-drop-status]')?.classList.remove("drag-over"));
	document.addEventListener("drop", event => {
		const column = event.target.closest('[data-drop-status]');
		if (!column) return;
		event.preventDefault();
		column.classList.remove("drag-over");
		const id = event.dataTransfer.getData("text/plain");
		if (id) moveCandidate(id, column.dataset.dropStatus);
	});
	document.addEventListener("click", async event => {
		const target = event.target.closest("button,[data-candidate-id]");
		if (!target) return;
		if (target.dataset.candidateId && !target.dataset.dragCandidate) openCandidate(target.dataset.candidateId);
		if (target.dataset.dragCandidate) openCandidate(target.dataset.candidateId);
		if (target.dataset.action === "close-job-editor") $("#job-editor").classList.add("hidden");
		if (target.dataset.action === "select-job") selectJob(target.dataset.jobKey);
		if (target.dataset.action === "edit-job") editJob(target.dataset.jobKey);
		if (target.dataset.action === "close-drawer") closeDrawer();
		if (target.dataset.action === "save-status") saveCandidateStatus(target.dataset.evaluationId);
		if (target.dataset.action === "generate-reply") generateReply(target.dataset.evaluationId);
		if (target.dataset.action === "show-pipeline") setView("pipeline");
		if (target.dataset.action === "show-activity") setView("activity");
		if (target.dataset.taskId) {
			const task = await api(`/api/tasks/${encodeURIComponent(target.dataset.taskId)}`);
			if (["screen-local", "screen-boss"].includes(task.kind) && task.result) { renderScreenResult(task.result); setView("screening"); }
			else toast(task.error?.message || task.message || "任务详情已加载", task.status === "failed" ? "error" : "success");
		}
		if (target.dataset.copyText !== undefined) { await navigator.clipboard.writeText(target.dataset.copyText); toast("已复制到剪贴板"); }
	});
	document.addEventListener("keydown", event => {
		if (event.target.matches("input,textarea,select")) return;
		const views = ["dashboard", "jobs", "screening", "pipeline", "replies", "activity", "settings"];
		const index = Number(event.key) - 1;
		if (index >= 0 && index < views.length) setView(views[index]);
		if (event.key === "Escape") closeDrawer();
	});
}

bindEvents();
bootstrap();
