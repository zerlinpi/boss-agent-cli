(() => {
	const FIRST_RUN_SESSION_KEY = "boss-autopilot-first-run-defaults";
	const ADVANCED_NAV_SESSION_KEY = "boss-recruit-advanced-nav";

	function setupState() {
		const data = state.bootstrap || {};
		return {
			aiReady: Boolean(data.ai?.configured),
			authReady: Boolean(data.auth?.logged_in) && data.auth?.state === "complete",
			modeReady: data.operating_mode === "research",
			hasCandidates: Boolean(data.onboarding?.has_candidates),
		};
	}

	function scrollTo(selector) {
		setTimeout(() => {
			const target = $(selector);
			if (!target) return;
			target.scrollIntoView({ behavior: "smooth", block: "center" });
			if (typeof target.focus === "function") target.focus({ preventScroll: true });
		}, 60);
	}

	function applySafeFirstRunDefaults({ announce = false } = {}) {
		const values = {
			"#autopilot-max-pages": "1",
			"#autopilot-max-candidates": "5",
			"#autopilot-refresh-hours": "0",
			"#autopilot-draft-top": "2",
		};
		let changed = false;
		for (const [selector, value] of Object.entries(values)) {
			const input = $(selector);
			if (!input) continue;
			input.value = value;
			changed = true;
		}
		const chat = $("#autopilot-include-chat");
		if (chat) chat.checked = false;
		const force = $("#autopilot-force");
		if (force) force.checked = false;
		const autoConfigure = $("#autopilot-auto-configure");
		if (autoConfigure) autoConfigure.checked = true;
		if (changed) sessionStorage.setItem(FIRST_RUN_SESSION_KEY, "1");
		if (announce && changed) {
			toast("已填入首次验证参数：1 页 / 5 人 / 2 草稿。确认后点击“运行全职位 Autopilot”");
		}
		return changed;
	}

	function simplifyNavigation() {
		const nav = $(".nav-list");
		if (!nav) return;
		const primary = ["dashboard", "screening", "pipeline", "replies", "settings"];
		const advanced = ["jobs", "activity"];
		const labels = {
			dashboard: "概览",
			screening: "自动筛选",
			pipeline: "候选人",
			replies: "回复草稿",
			settings: "设置",
			jobs: "岗位与规则",
			activity: "任务与审计",
		};

		for (const [index, view] of primary.entries()) {
			const item = nav.querySelector(`[data-view="${view}"]`);
			if (!item) continue;
			item.classList.remove("product-advanced-nav");
			const text = item.querySelectorAll("span")[1];
			if (text) text.textContent = labels[view];
			const key = item.querySelector("kbd");
			if (key) key.textContent = String(index + 1);
			nav.append(item);
		}

		let toggle = $("#product-advanced-toggle");
		if (!toggle) {
			toggle = document.createElement("button");
			toggle.id = "product-advanced-toggle";
			toggle.type = "button";
			toggle.className = "nav-item product-advanced-toggle";
			toggle.innerHTML = '<span class="nav-icon">⋯</span><span>高级功能</span><kbd>+</kbd>';
			nav.append(toggle);
		}

		const expanded = sessionStorage.getItem(ADVANCED_NAV_SESSION_KEY) === "1";
		toggle.classList.toggle("active", expanded);
		for (const view of advanced) {
			const item = nav.querySelector(`[data-view="${view}"]`);
			if (!item) continue;
			item.classList.add("product-advanced-nav");
			item.classList.toggle("hidden", !expanded);
			const text = item.querySelectorAll("span")[1];
			if (text) text.textContent = labels[view];
			const key = item.querySelector("kbd");
			if (key) key.textContent = "";
			nav.append(item);
		}
	}

	function toggleAdvancedNavigation() {
		const toggle = $("#product-advanced-toggle");
		if (!toggle) return;
		const open = sessionStorage.getItem(ADVANCED_NAV_SESSION_KEY) !== "1";
		sessionStorage.setItem(ADVANCED_NAV_SESSION_KEY, open ? "1" : "0");
		toggle.classList.toggle("active", open);
		$$('.product-advanced-nav').forEach(item => item.classList.toggle("hidden", !open));
	}

	function simplifyScreeningChoices() {
		const grid = $(".screening-grid");
		const autopilot = $("#autopilot-panel");
		if (!grid || !autopilot) return;

		if (grid.firstElementChild !== autopilot) grid.prepend(autopilot);
		if ($("#advanced-screening-options")) return;

		const secondaryPanels = [...grid.children].filter(node => node.classList?.contains("action-panel") && node !== autopilot);
		if (!secondaryPanels.length) return;

		const details = document.createElement("details");
		details.id = "advanced-screening-options";
		details.className = "panel screening-advanced";
		details.innerHTML = `
			<summary>高级筛选方式 <span>本地文件 / 单岗位</span></summary>
			<p>主流程优先使用全职位 Autopilot。只有需要手工上传简历，或明确只处理一个 BOSS 职位时再展开这里。</p>
			<div class="screening-advanced-grid"></div>
		`;
		grid.append(details);
		const advancedGrid = details.querySelector(".screening-advanced-grid");
		for (const panel of secondaryPanels) advancedGrid?.append(panel);
	}

	function openSetupTarget(action) {
		if (action === "ai") {
			setView("settings");
			scrollTo("#ai-form");
			return;
		}
		if (action === "auth") {
			setView("settings");
			scrollTo("#login-button");
			return;
		}
		if (action === "mode") {
			setView("settings");
			scrollTo('input[name="operating_mode"][value="research"]');
			toast("请选择 Research，并确认已获得候选人数据处理授权");
			return;
		}
		if (action === "first-run") {
			setView("screening");
			setTimeout(() => {
				simplifyScreeningChoices();
				applySafeFirstRunDefaults({ announce: true });
				const panel = $("#autopilot-panel");
				if (panel) panel.scrollIntoView({ behavior: "smooth", block: "start" });
			}, 80);
			return;
		}
		if (action === "screening") {
			setView("screening");
			setTimeout(() => $("#autopilot-panel")?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
			return;
		}
		if (action === "candidates") setView("pipeline");
	}

	function renderAuthQuality() {
		const auth = state.bootstrap?.auth || {};
		if (!auth.logged_in || auth.state === "complete") return;
		const recovery = auth.health?.recovery_action || "请重新登录或使用 Chrome CDP 刷新完整登录态";
		const sidebar = $("#sidebar-auth-text");
		if (sidebar) sidebar.textContent = "BOSS 登录待刷新";
		const system = $("#system-auth");
		if (system) system.textContent = "登录态不完整";
		const description = $("#auth-description");
		if (description) description.textContent = `登录态不完整（${auth.state || "partial"}）。${recovery}`;
		const badge = $("#auth-badge");
		if (badge) setBadge(badge, "需刷新", "manual_review");
	}

	function renderPrimaryAction(snapshot) {
		const button = $('[data-action="open-screening"]');
		if (!button) return;
		const picker = $(".job-picker");
		if (picker) picker.classList.toggle("hidden", !state.jobs.length);
		let action = "screening";
		let label = "运行 Autopilot";
		if (!snapshot.aiReady) {
			action = "ai";
			label = "配置 AI";
		} else if (!snapshot.authReady) {
			action = "auth";
			label = "登录 BOSS";
		} else if (!snapshot.modeReady) {
			action = "mode";
			label = "启用 Research";
		} else if (!snapshot.hasCandidates) {
			action = "first-run";
			label = "运行 5 人验证";
		}
		button.dataset.productPrimaryAction = action;
		button.textContent = label;
	}

	function renderAutopilotReadiness(snapshot) {
		const panel = $("#autopilot-panel");
		if (!panel) return;
		let node = $("#autopilot-readiness");
		if (!node) {
			node = document.createElement("div");
			node.id = "autopilot-readiness";
			node.className = "autopilot-human-note";
			const heading = panel.querySelector(".autopilot-heading");
			if (heading) heading.insertAdjacentElement("afterend", node);
			else panel.prepend(node);
		}
		const items = [
			["AI", snapshot.aiReady],
			["BOSS 凭证完整", snapshot.authReady],
			["Research", snapshot.modeReady],
		];
		const ready = snapshot.aiReady && snapshot.authReady && snapshot.modeReady;
		if (ready && !snapshot.hasCandidates && !sessionStorage.getItem(FIRST_RUN_SESSION_KEY)) {
			applySafeFirstRunDefaults();
		}
		node.innerHTML = `<strong>运行前检查：</strong> ${items.map(([label, done]) => `${done ? "✓" : "○"} ${label}`).join(" · ")}${ready && !snapshot.hasCandidates ? '<br><button type="button" class="button secondary compact-button" data-guide-action="first-run">恢复首次 5 人测试参数</button>' : ""}`;
	}

	function renderGuide() {
		simplifyNavigation();
		simplifyScreeningChoices();
		if (!state.bootstrap) return;
		const onboarding = $("#onboarding");
		if (!onboarding) return;
		const snapshot = setupState();
		renderAuthQuality();
		renderPrimaryAction(snapshot);
		renderAutopilotReadiness(snapshot);
		if (snapshot.hasCandidates) {
			onboarding.classList.add("hidden");
			return;
		}

		const steps = [
			{ action: "ai", label: "配置 AI", done: snapshot.aiReady },
			{ action: "auth", label: "登录 BOSS", done: snapshot.authReady },
			{ action: "mode", label: "启用 Research", done: snapshot.modeReady },
			{ action: "first-run", label: "5 人验证", done: snapshot.hasCandidates },
		];
		const next = !snapshot.aiReady ? "ai" : !snapshot.authReady ? "auth" : !snapshot.modeReady ? "mode" : "first-run";
		const nextLabel = {
			ai: "下一步：配置 AI",
			auth: "下一步：登录 BOSS",
			mode: "下一步：启用 Research",
			"first-run": "下一步：运行 5 人安全测试",
		}[next];

		onboarding.classList.remove("hidden");
		onboarding.innerHTML = `
			<div>
				<p class="eyebrow">QUICK START</p>
				<h2>第一次使用只完成这 4 步</h2>
				<p style="margin:6px 0 0;color:rgba(255,255,255,.78);font-size:12px;">先验证 5 位候选人的真实链路，确认结果后再扩大范围。</p>
			</div>
			<div class="onboarding-steps">
				${steps.map((step, index) => `<button type="button" class="${step.done ? "done" : ""}" data-guide-action="${step.action}"><i>${index + 1}</i><span>${step.label}</span></button>`).join("")}
				<button type="button" class="button primary" data-guide-action="${next}">${nextLabel}</button>
			</div>
		`;
	}

	document.addEventListener("click", event => {
		const advancedToggle = event.target.closest("#product-advanced-toggle");
		if (advancedToggle) {
			event.preventDefault();
			event.stopImmediatePropagation();
			toggleAdvancedNavigation();
			return;
		}
		const primary = event.target.closest('[data-product-primary-action]');
		if (primary) {
			event.preventDefault();
			event.stopImmediatePropagation();
			openSetupTarget(primary.dataset.productPrimaryAction || "screening");
			return;
		}
		const button = event.target.closest("[data-guide-action]");
		if (!button) return;
		event.preventDefault();
		event.stopImmediatePropagation();
		openSetupTarget(button.dataset.guideAction || "");
	}, true);

	const originalApplyBootstrap = applyBootstrap;
	applyBootstrap = function guidedApplyBootstrap() {
		const result = originalApplyBootstrap();
		setTimeout(renderGuide, 0);
		return result;
	};

	setTimeout(renderGuide, 0);
})();
