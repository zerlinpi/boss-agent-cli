(() => {
	if (window.__bossProductWorkbenchInstalled) return;
	window.__bossProductWorkbenchInstalled = true;

	const COMBINED_INTERVIEW_FILTER = "product_interview_any";
	const INTERVIEW_RECOMMENDATIONS = new Set(["strong_interview", "interview"]);
	const DAY_MS = 24 * 60 * 60 * 1000;

	function candidates() {
		return Array.isArray(state.candidates) ? state.candidates : [];
	}

	function replies() {
		return Array.isArray(state.replies) ? state.replies : [];
	}

	function auditItems() {
		return Array.isArray(state.audit) ? state.audit : [];
	}

	function readinessState() {
		const bootstrap = state.bootstrap || {};
		const auth = bootstrap.auth || {};
		return {
			ai: Boolean(bootstrap.ai?.configured),
			auth: Boolean(auth.logged_in) && auth.state === "complete",
			mode: bootstrap.operating_mode === "research",
		};
	}

	function readinessCount() {
		return Object.values(readinessState()).filter(Boolean).length;
	}

	function activeJobLabel() {
		const job = typeof activeJobRecord === "function" ? activeJobRecord() : null;
		return job?.title || job?.metadata?.title || state.activeJob || "尚未选择岗位";
	}

	function ensureCombinedInterviewFilter() {
		const select = $("#candidate-recommendation-filter");
		if (!select || select.querySelector(`option[value="${COMBINED_INTERVIEW_FILTER}"]`)) return;
		const option = document.createElement("option");
		option.value = COMBINED_INTERVIEW_FILTER;
		option.textContent = "建议面试（含强烈）";
		const manual = select.querySelector('option[value="manual_review"]');
		if (manual) select.insertBefore(option, manual);
		else select.append(option);
	}

	const originalFilteredCandidates = filteredCandidates;
	filteredCandidates = function productFilteredCandidates() {
		const select = $("#candidate-recommendation-filter");
		if (!select || select.value !== COMBINED_INTERVIEW_FILTER) return originalFilteredCandidates();
		const selected = select.value;
		select.value = "";
		try {
			return originalFilteredCandidates().filter(candidate => INTERVIEW_RECOMMENDATIONS.has(candidate.recommendation));
		} finally {
			select.value = selected;
		}
	};

	function ensureActionCenter() {
		let panel = $("#product-action-center");
		if (panel) return panel;
		const dashboard = $('[data-view-panel="dashboard"]');
		const metrics = dashboard?.querySelector(".metrics-grid");
		if (!dashboard || !metrics) return null;

		panel = document.createElement("section");
		panel.id = "product-action-center";
		panel.className = "product-ops-workbench";
		panel.setAttribute("aria-label", "今日招聘待处理");
		panel.innerHTML = `
			<div class="product-ops-head">
				<div>
					<p class="eyebrow">RECRUITER QUEUE</p>
					<h2>今日待处理</h2>
					<p>把 AI 结果收敛为人工审核队列；最终招聘判断和消息发送仍由招聘人员完成。</p>
				</div>
				<span class="product-context-chip" id="product-active-job">尚未选择岗位</span>
			</div>
			<div class="product-ops-grid">
				<button type="button" class="product-ops-card" data-product-action="manual-review">
					<span>待人工复核</span><strong id="product-manual-review-count">0</strong>
					<small>优先核对证据、风险和待确认项</small>
				</button>
				<button type="button" class="product-ops-card" data-product-action="interview-review">
					<span>建议面试待确认</span><strong id="product-interview-count">0</strong>
					<small>包含“强烈建议”和“建议面试”，仅作人工复核线索</small>
				</button>
				<button type="button" class="product-ops-card" data-product-action="replies">
					<span>草稿待审核</span><strong id="product-reply-count">0</strong>
					<small>本地回复草稿不会自动发送</small>
				</button>
				<button type="button" class="product-ops-card product-readiness-card" data-product-action="readiness">
					<span>运行准备度</span><strong id="product-readiness-count">0/3</strong>
					<small id="product-readiness-hint">检查 AI、BOSS 登录和 Research</small>
				</button>
			</div>
			<div class="product-activity-block">
				<div class="product-activity-heading">
					<div><strong>近 7 天操作</strong><span>来自本机审计记录，用于快速判断招聘工作节奏</span></div>
					<button type="button" class="text-button" data-product-action="activity">查看审计</button>
				</div>
				<div id="product-activity-strip" class="product-activity-strip" aria-label="近七天操作数量"></div>
			</div>
		`;
		metrics.insertAdjacentElement("afterend", panel);
		return panel;
	}

	function renderActivityStrip() {
		const strip = $("#product-activity-strip");
		if (!strip) return;
		const today = new Date();
		today.setHours(0, 0, 0, 0);
		const days = [];
		for (let offset = 6; offset >= 0; offset -= 1) {
			const date = new Date(today.getTime() - offset * DAY_MS);
			days.push({
				date,
				key: `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`,
				count: 0,
			});
		}
		const counts = new Map(days.map(day => [day.key, day]));
		for (const item of auditItems()) {
			const date = new Date(item.created_at || "");
			if (Number.isNaN(date.getTime())) continue;
			const key = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
			const day = counts.get(key);
			if (day) day.count += 1;
		}
		const maximum = Math.max(1, ...days.map(day => day.count));
		strip.innerHTML = days.map(day => {
			const weekday = day.date.toLocaleDateString("zh-CN", { weekday: "short" });
			const dateLabel = day.date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
			const height = Math.max(day.count ? 18 : 5, Math.round(day.count / maximum * 100));
			return `<div class="product-activity-day" title="${dateLabel} · ${day.count} 条操作"><span>${escapeHtml(weekday)}</span><div class="product-activity-track"><i style="--activity-height:${height}%"></i></div><strong>${day.count}</strong><small>${escapeHtml(dateLabel)}</small></div>`;
		}).join("");
	}

	function renderActionCenter() {
		if (!ensureActionCenter()) return;
		const items = candidates();
		const manualReview = items.filter(candidate => candidate.recommendation === "manual_review").length;
		const interview = items.filter(candidate => INTERVIEW_RECOMMENDATIONS.has(candidate.recommendation)).length;
		const readiness = readinessState();
		const readyCount = readinessCount();
		const nextHint = !readiness.ai
			? "下一步：配置 AI 服务"
			: !readiness.auth
				? "下一步：完成 BOSS 登录"
				: !readiness.mode
					? "下一步：确认授权后启用 Research"
					: "已就绪，可运行 Autopilot";

		$("#product-active-job").textContent = activeJobLabel();
		$("#product-manual-review-count").textContent = String(manualReview);
		$("#product-interview-count").textContent = String(interview);
		$("#product-reply-count").textContent = String(replies().length);
		$("#product-readiness-count").textContent = `${readyCount}/3`;
		$("#product-readiness-hint").textContent = nextHint;
		const readinessCard = $(".product-readiness-card");
		if (readinessCard) readinessCard.dataset.ready = readyCount === 3 ? "1" : "0";
		renderActivityStrip();
	}

	function ensureReviewQueue() {
		ensureCombinedInterviewFilter();
		let queue = $("#product-review-queue");
		if (queue) return queue;
		const toolbar = $(".filter-toolbar");
		if (!toolbar) return null;
		queue = document.createElement("section");
		queue.id = "product-review-queue";
		queue.className = "product-review-queue";
		queue.setAttribute("aria-label", "候选人人工审核队列");
		queue.innerHTML = `
			<div class="product-review-copy">
				<p class="eyebrow">REVIEW QUEUE</p>
				<h3>人工审核队列</h3>
				<span>AI 只提供证据与优先级，不替代最终招聘判断。</span>
			</div>
			<div class="product-review-filters" role="group" aria-label="候选人快速筛选">
				<button type="button" data-review-preset="all">全部 <strong data-review-count="all">0</strong></button>
				<button type="button" data-review-preset="manual_review">人工复核 <strong data-review-count="manual_review">0</strong></button>
				<button type="button" data-review-preset="interview_any">建议面试 <strong data-review-count="interview_any">0</strong></button>
				<button type="button" data-review-preset="new">新候选人 <strong data-review-count="new">0</strong></button>
			</div>
		`;
		toolbar.insertAdjacentElement("beforebegin", queue);
		return queue;
	}

	function activeReviewPreset() {
		const search = $("#candidate-search")?.value.trim() || "";
		const status = $("#candidate-status-filter")?.value || "";
		const recommendation = $("#candidate-recommendation-filter")?.value || "";
		if (!search && !status && !recommendation) return "all";
		if (!search && !status && recommendation === "manual_review") return "manual_review";
		if (!search && !status && recommendation === COMBINED_INTERVIEW_FILTER) return "interview_any";
		if (!search && status === "new" && !recommendation) return "new";
		return "custom";
	}

	function renderReviewQueue() {
		if (!ensureReviewQueue()) return;
		const items = candidates();
		const counts = {
			all: items.length,
			manual_review: items.filter(candidate => candidate.recommendation === "manual_review").length,
			interview_any: items.filter(candidate => INTERVIEW_RECOMMENDATIONS.has(candidate.recommendation)).length,
			new: items.filter(candidate => (candidate.status || "new") === "new").length,
		};
		for (const [key, value] of Object.entries(counts)) {
			const node = $(`[data-review-count="${key}"]`);
			if (node) node.textContent = String(value);
		}
		const active = activeReviewPreset();
		$$('[data-review-preset]').forEach(button => {
			const selected = button.dataset.reviewPreset === active;
			button.classList.toggle("active", selected);
			button.setAttribute("aria-pressed", String(selected));
		});
	}

	function applyReviewPreset(preset) {
		const search = $("#candidate-search");
		const status = $("#candidate-status-filter");
		const recommendation = $("#candidate-recommendation-filter");
		const sort = $("#candidate-sort");
		if (search) search.value = "";
		if (status) status.value = preset === "new" ? "new" : "";
		if (recommendation) {
			recommendation.value = preset === "manual_review"
				? "manual_review"
				: preset === "interview_any"
					? COMBINED_INTERVIEW_FILTER
					: "";
		}
		if (sort) sort.value = "score-desc";
		renderCandidateViews();
	}

	function readinessChip(label, ready) {
		return `<span class="product-readiness-chip ${ready ? "ready" : "blocked"}"><i>${ready ? "✓" : "!"}</i>${label}</span>`;
	}

	function ensureAutopilotRunPlan() {
		let plan = $("#autopilot-run-plan");
		if (plan) return plan;
		const panel = $("#autopilot-panel");
		const button = $("#autopilot-run-button");
		if (!panel || !button) return null;
		plan = document.createElement("section");
		plan.id = "autopilot-run-plan";
		plan.className = "autopilot-run-plan";
		plan.setAttribute("aria-label", "Autopilot 运行前检查");
		plan.setAttribute("aria-live", "polite");
		button.insertAdjacentElement("beforebegin", plan);

		for (const selector of [
			"#autopilot-max-pages",
			"#autopilot-max-candidates",
			"#autopilot-refresh-hours",
			"#autopilot-draft-top",
			"#autopilot-auto-configure",
			"#autopilot-include-chat",
			"#autopilot-force",
		]) {
			const control = $(selector);
			if (!control || control.dataset.productRunPlanBound === "1") continue;
			control.dataset.productRunPlanBound = "1";
			control.addEventListener(control.matches('input[type="checkbox"]') ? "change" : "input", renderAutopilotRunPlan);
		}
		return plan;
	}

	function numberFrom(selector, fallback) {
		const value = Number($(selector)?.value);
		return Number.isFinite(value) ? value : fallback;
	}

	function renderAutopilotRunPlan() {
		const plan = ensureAutopilotRunPlan();
		if (!plan) return;
		const readiness = readinessState();
		const pages = numberFrom("#autopilot-max-pages", 30);
		const candidateLimit = numberFrom("#autopilot-max-candidates", 2000);
		const draftTop = numberFrom("#autopilot-draft-top", 10);
		const refreshHours = numberFrom("#autopilot-refresh-hours", 24);
		const includeChat = Boolean($("#autopilot-include-chat")?.checked);
		const force = Boolean($("#autopilot-force")?.checked);
		const autoConfigure = Boolean($("#autopilot-auto-configure")?.checked);
		const allReady = readiness.ai && readiness.auth && readiness.mode;

		plan.dataset.ready = allReady ? "1" : "0";
		plan.innerHTML = `
			<div class="autopilot-run-plan-head">
				<div><strong>运行前检查</strong><span>${allReady ? "前置条件已满足" : "先完成缺失条件，再启动全职位同步"}</span></div>
				<span class="product-human-boundary">自动发送消息：0</span>
			</div>
			<div class="product-readiness-chips">
				${readinessChip("AI 已配置", readiness.ai)}
				${readinessChip("BOSS 登录完整", readiness.auth)}
				${readinessChip("Research 已授权", readiness.mode)}
			</div>
			<div class="autopilot-run-scope">
				<div><span>读取范围</span><strong>${pages} 页 / 职位 · 最多 ${candidateLimit} 人 / 职位</strong></div>
				<div><span>输出</span><strong>每职位 ${draftTop} 份草稿 · ${autoConfigure ? "自动维护岗位画像" : "仅使用现有岗位"}</strong></div>
				<div><span>复查策略</span><strong>${refreshHours === 0 ? "本轮允许立即复查" : `${refreshHours} 小时内已处理候选人跳过`} · ${includeChat ? "读取聊天上下文" : "不读取聊天上下文"}</strong></div>
			</div>
			${force ? '<div class="autopilot-run-warning"><strong>已开启强制重评</strong><span>会重新拉取并评估已处理候选人；建议仅在规则或数据发生明显变化时使用。</span></div>' : ""}
			<p class="autopilot-run-boundary">AI 只生成岗位画像、证据化评估、排序和回复草稿；最终阶段更新、淘汰/录用判断和消息发送保持人工操作。</p>
		`;
	}

	function watchAutopilotPanel() {
		if (ensureAutopilotRunPlan()) {
			renderAutopilotRunPlan();
			return;
		}
		const grid = $(".screening-grid");
		if (!grid) return;
		const observer = new MutationObserver(() => {
			if (!ensureAutopilotRunPlan()) return;
			observer.disconnect();
			renderAutopilotRunPlan();
		});
		observer.observe(grid, { childList: true, subtree: true });
	}

	function enhanceCandidateDrawer(record) {
		const content = $("#drawer-content");
		if (!content) return;
		const evaluation = record?.evaluation || {};
		const dimensions = Array.isArray(evaluation.dimensions) ? evaluation.dimensions.length : 0;
		const concerns = Array.isArray(evaluation.concerns) ? evaluation.concerns.length : 0;
		const questions = Array.isArray(evaluation.next_questions) ? evaluation.next_questions.length : 0;
		const score = content.querySelector(".detail-score");
		if (score && !content.querySelector(".product-evidence-rail")) {
			score.insertAdjacentHTML("afterend", `
				<div class="product-evidence-rail" aria-label="人工审核摘要">
					<div><span>AI 评分依据</span><strong>${dimensions} 项维度</strong></div>
					<div><span>待确认风险</span><strong>${concerns} 项</strong></div>
					<div><span>建议追问</span><strong>${questions} 项</strong></div>
					<div class="human"><span>最终判断</span><strong>人工确认</strong></div>
				</div>
				<p class="product-evidence-guidance">建议先核对风险、评分理由和原始简历证据，再更新人工阶段；不要仅依据总分做最终招聘决定。</p>
			`);
		}
		for (const section of content.querySelectorAll(".detail-section")) {
			const title = section.querySelector("h3")?.textContent || "";
			section.classList.toggle("product-evidence-section", title.includes("评分维度"));
			section.classList.toggle("product-human-decision-section", title.includes("人工状态"));
			section.classList.toggle("product-reply-section", title.includes("回复草稿"));
		}
	}

	function openNextReadinessStep() {
		const readiness = readinessState();
		if (!readiness.ai) {
			setView("settings");
			setTimeout(() => $("#ai-form")?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);
			return;
		}
		if (!readiness.auth) {
			setView("settings");
			setTimeout(() => $("#login-button")?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);
			return;
		}
		if (!readiness.mode) {
			setView("settings");
			setTimeout(() => $('input[name="operating_mode"][value="research"]')?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);
			return;
		}
		setView("screening");
		setTimeout(() => $("#autopilot-panel")?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
	}

	function openAdvancedView(view) {
		const toggle = $("#product-advanced-toggle");
		if (toggle && toggle.getAttribute("aria-expanded") !== "true") toggle.click();
		setView(view);
	}

	function goToCandidatePreset(preset) {
		setView("pipeline");
		setTimeout(() => applyReviewPreset(preset), 0);
	}

	const originalRenderDashboard = renderDashboard;
	renderDashboard = function productRenderDashboard(...args) {
		const result = originalRenderDashboard(...args);
		renderActionCenter();
		return result;
	};

	const originalRenderCandidateViews = renderCandidateViews;
	renderCandidateViews = function productRenderCandidateViews() {
		const result = originalRenderCandidateViews();
		renderReviewQueue();
		renderActionCenter();
		return result;
	};

	const originalRenderReplies = renderReplies;
	renderReplies = function productRenderReplies() {
		const result = originalRenderReplies();
		renderActionCenter();
		return result;
	};

	const originalRenderAudit = renderAudit;
	renderAudit = function productRenderAudit() {
		const result = originalRenderAudit();
		renderActionCenter();
		return result;
	};

	const originalApplyBootstrap = applyBootstrap;
	applyBootstrap = function productApplyBootstrap() {
		const result = originalApplyBootstrap();
		renderActionCenter();
		renderAutopilotRunPlan();
		return result;
	};

	const originalRenderCandidateDrawer = renderCandidateDrawer;
	renderCandidateDrawer = function productRenderCandidateDrawer(record) {
		const result = originalRenderCandidateDrawer(record);
		enhanceCandidateDrawer(record);
		return result;
	};

	const originalSetView = setView;
	setView = function productSetView(name) {
		const result = originalSetView(name);
		setTimeout(() => {
			renderActionCenter();
			renderReviewQueue();
			renderAutopilotRunPlan();
		}, 0);
		return result;
	};

	document.addEventListener("click", event => {
		const presetButton = event.target.closest?.("[data-review-preset]");
		if (presetButton) {
			event.preventDefault();
			applyReviewPreset(presetButton.dataset.reviewPreset || "all");
			return;
		}

		const action = event.target.closest?.("[data-product-action]")?.dataset.productAction;
		if (!action) return;
		event.preventDefault();
		if (action === "manual-review") goToCandidatePreset("manual_review");
		else if (action === "interview-review") goToCandidatePreset("interview_any");
		else if (action === "replies") setView("replies");
		else if (action === "readiness") openNextReadinessStep();
		else if (action === "activity") openAdvancedView("activity");
	});

	for (const selector of ["#candidate-search", "#candidate-status-filter", "#candidate-recommendation-filter"]) {
		const control = $(selector);
		if (!control) continue;
		control.addEventListener(selector === "#candidate-search" ? "input" : "change", () => setTimeout(renderReviewQueue, 0));
	}

	document.addEventListener("click", event => {
		if (!event.target.closest?.('[data-action="open-screening"], [data-view="screening"]')) return;
		setTimeout(renderAutopilotRunPlan, 160);
	});

	ensureCombinedInterviewFilter();
	ensureActionCenter();
	ensureReviewQueue();
	watchAutopilotPanel();
	setTimeout(() => {
		renderActionCenter();
		renderReviewQueue();
		renderAutopilotRunPlan();
	}, 0);
})();