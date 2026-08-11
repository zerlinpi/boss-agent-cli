(() => {
	const FIRST_RUN_SESSION_KEY = "boss-autopilot-first-run-defaults";

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
				applySafeFirstRunDefaults({ announce: true });
				const panel = $("#autopilot-panel");
				if (panel) panel.scrollIntoView({ behavior: "smooth", block: "start" });
			}, 80);
			return;
		}
		if (action === "candidates") {
			setView("pipeline");
		}
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
		if (!state.bootstrap) return;
		const onboarding = $("#onboarding");
		if (!onboarding) return;
		const snapshot = setupState();
		renderAuthQuality();
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
