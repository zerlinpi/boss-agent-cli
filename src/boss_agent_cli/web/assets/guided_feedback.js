(() => {
	function candidateFiltersActive() {
		return Boolean(
			$("#candidate-search")?.value.trim()
			|| $("#candidate-status-filter")?.value
			|| $("#candidate-recommendation-filter")?.value
		);
	}

	function ensureCandidateWorkbenchStatus() {
		let node = $("#candidate-workbench-status");
		if (node) return node;
		const toolbar = $(".filter-toolbar");
		if (!toolbar) return null;
		node = document.createElement("div");
		node.id = "candidate-workbench-status";
		node.className = "candidate-workbench-status";
		node.setAttribute("role", "status");
		node.setAttribute("aria-live", "polite");
		toolbar.insertAdjacentElement("afterend", node);
		return node;
	}

	function setCandidateBusy(busy) {
		const table = $("#pipeline-table");
		const kanban = $("#pipeline-kanban");
		for (const node of [table, kanban]) {
			if (!node) continue;
			node.setAttribute("aria-busy", String(busy));
			node.classList.toggle("is-loading", busy);
		}
		const status = ensureCandidateWorkbenchStatus();
		if (status) status.dataset.loading = busy ? "1" : "0";
	}

	function syncCandidateWorkbenchStatus() {
		const status = ensureCandidateWorkbenchStatus();
		if (!status) return;
		if (status.dataset.loading === "1") {
			status.innerHTML = '<span><strong>正在读取候选人…</strong> 请稍候</span>';
			return;
		}

		if (!state.activeJob) {
			status.innerHTML = '<span><strong>尚未选择岗位</strong> · 运行 Autopilot 后会自动建立岗位并同步候选人</span><button type="button" class="text-button" data-feedback-action="screening">前往自动筛选</button>';
			return;
		}

		const total = Array.isArray(state.candidates) ? state.candidates.length : 0;
		const visible = typeof filteredCandidates === "function" ? filteredCandidates().length : total;
		const filtered = candidateFiltersActive();
		status.innerHTML = `
			<span><strong>${visible}</strong> / ${total} 位候选人${filtered ? " · 已应用筛选" : ""}</span>
			${filtered ? '<button type="button" class="text-button" data-feedback-clear-filters>清除筛选</button>' : ""}
		`;

		const empty = $("#candidate-empty");
		if (!empty || visible > 0) return;
		if (total === 0) {
			empty.innerHTML = '当前岗位暂无候选人。<br><button type="button" class="button primary compact-button" data-feedback-action="screening">运行 Autopilot 同步最新投递</button>';
		} else {
			empty.innerHTML = '没有符合当前筛选条件的候选人。<br><button type="button" class="button ghost compact-button" data-feedback-clear-filters>清除筛选</button>';
		}
	}

	function ensureTaskRecoveryPanel() {
		let panel = $("#task-recovery-panel");
		if (panel) return panel;
		const banner = $("#task-banner");
		if (!banner) return null;
		panel = document.createElement("section");
		panel.id = "task-recovery-panel";
		panel.className = "task-recovery-panel hidden";
		panel.setAttribute("role", "alert");
		panel.setAttribute("aria-live", "assertive");
		banner.insertAdjacentElement("afterend", panel);
		return panel;
	}

	function recoveryForTask(task) {
		const code = String(task?.error?.code || "TASK_FAILED");
		if (code === "AUTH_REQUIRED" || code === "AUTH_INCOMPLETE") {
			return { action: "auth", label: "重新登录 BOSS", hint: "登录态缺失或不完整，刷新登录后再重新运行。" };
		}
		if (code === "COMPLIANCE_BLOCKED") {
			return { action: "mode", label: "检查 Research", hint: "当前模式不允许读取候选人数据，请确认授权后再启用 Research。" };
		}
		if (code.includes("AI") || code === "CONFIG_REQUIRED") {
			return { action: "ai", label: "检查 AI 配置", hint: "AI 服务配置不可用，请检查模型、API Key 或 Base URL。" };
		}
		if (code === "SCREENING_ALREADY_RUNNING" || code === "AUTOPILOT_BUSY") {
			return { action: "activity", label: "查看运行任务", hint: "已有筛选任务占用执行通道，先查看当前任务状态。" };
		}
		return { action: "screening", label: "返回自动筛选", hint: "检查错误信息后调整参数，再由人工重新启动任务。" };
	}

	function renderTaskRecovery(task) {
		const panel = ensureTaskRecoveryPanel();
		if (!panel) return;
		if (task?.status !== "failed") {
			if (task?.status === "completed") {
				panel.classList.add("hidden");
				panel.innerHTML = "";
			}
			return;
		}
		const recovery = recoveryForTask(task);
		const code = String(task.error?.code || "TASK_FAILED");
		const message = String(task.error?.message || task.message || "任务执行失败");
		panel.classList.remove("hidden");
		panel.innerHTML = `
			<div>
				<strong>任务未完成</strong>
				<p>${escapeHtml(message)}</p>
				<small>${escapeHtml(code)} · ${escapeHtml(recovery.hint)}</small>
			</div>
			<div class="task-recovery-actions">
				<button type="button" class="button primary compact-button" data-feedback-action="${recovery.action}">${recovery.label}</button>
				<button type="button" class="button ghost compact-button" data-feedback-dismiss>关闭</button>
			</div>
		`;
	}

	function navigateFeedback(action) {
		if (["ai", "auth", "mode"].includes(action)) {
			setView("settings");
			const selector = action === "ai"
				? "#ai-form"
				: action === "auth"
					? "#login-button"
					: 'input[name="operating_mode"][value="research"]';
			setTimeout(() => $(selector)?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);
			return;
		}
		if (action === "activity") {
			setView("activity");
			return;
		}
		if (action === "screening") {
			setView("screening");
			setTimeout(() => $("#autopilot-panel")?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
			return;
		}
		if (action === "candidates") setView("pipeline");
	}

	const originalRenderCandidateViews = renderCandidateViews;
	renderCandidateViews = function feedbackRenderCandidateViews() {
		const result = originalRenderCandidateViews();
		syncCandidateWorkbenchStatus();
		return result;
	};

	const originalLoadCandidates = loadCandidates;
	loadCandidates = async function feedbackLoadCandidates() {
		setCandidateBusy(true);
		syncCandidateWorkbenchStatus();
		try {
			return await originalLoadCandidates();
		} finally {
			setCandidateBusy(false);
			syncCandidateWorkbenchStatus();
		}
	};

	const originalRenderTask = renderTask;
	renderTask = function feedbackRenderTask(task) {
		const result = originalRenderTask(task);
		renderTaskRecovery(task);
		return result;
	};

	const originalWatchTask = watchTask;
	watchTask = function feedbackWatchTask(id) {
		const panel = ensureTaskRecoveryPanel();
		if (panel) {
			panel.classList.add("hidden");
			panel.innerHTML = "";
		}
		return originalWatchTask(id);
	};

	for (const selector of ["#candidate-search", "#candidate-status-filter", "#candidate-recommendation-filter"]) {
		const control = $(selector);
		if (!control) continue;
		control.addEventListener(selector === "#candidate-search" ? "input" : "change", () => {
			setTimeout(syncCandidateWorkbenchStatus, 0);
		});
	}

	document.addEventListener("click", event => {
		const action = event.target.closest?.("[data-feedback-action]")?.dataset.feedbackAction;
		if (action) {
			event.preventDefault();
			navigateFeedback(action);
			return;
		}
		if (event.target.closest?.("[data-feedback-clear-filters]")) {
			event.preventDefault();
			const search = $("#candidate-search");
			const status = $("#candidate-status-filter");
			const recommendation = $("#candidate-recommendation-filter");
			if (search) search.value = "";
			if (status) status.value = "";
			if (recommendation) recommendation.value = "";
			renderCandidateViews();
			return;
		}
		if (event.target.closest?.("[data-feedback-dismiss]")) {
			event.preventDefault();
			$("#task-recovery-panel")?.classList.add("hidden");
		}
	});

	setTimeout(syncCandidateWorkbenchStatus, 0);
})();
