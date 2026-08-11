(() => {
	const grid = $(".screening-grid");
	if (!grid || $("#autopilot-panel")) return;

	grid.insertAdjacentHTML("beforeend", `
		<article class="panel action-panel autopilot-panel" id="autopilot-panel">
			<div class="action-icon">AUTO</div>
			<div class="autopilot-heading">
				<div><p class="eyebrow">RECRUITER AUTOPILOT</p><h3>全职位增量同步</h3></div>
				<span class="badge manual_review">人工最终确认</span>
			</div>
			<p>自动读取 BOSS 当前职位和最新 JD，生成岗位画像与安全评分规则，逐页抓取新投递、解析简历、AI 评分、排名并生成回复草稿。不会自动淘汰、录用或发送消息。</p>
			<div class="compact-form">
				<div class="two-col">
					<label><span>每职位最大页数</span><input id="autopilot-max-pages" type="number" min="1" max="100" value="30"></label>
					<label><span>每职位候选人上限</span><input id="autopilot-max-candidates" type="number" min="1" max="10000" value="2000"></label>
				</div>
				<div class="two-col">
					<label><span>已处理复查间隔（小时）</span><input id="autopilot-refresh-hours" type="number" min="0" max="720" value="24"></label>
					<label><span>每职位生成草稿数</span><input id="autopilot-draft-top" type="number" min="0" max="100" value="10"></label>
				</div>
				<label class="check-row"><input id="autopilot-auto-configure" type="checkbox" checked><span>自动读取未配置 BOSS 职位的 JD、建立岗位并生成 AI 岗位画像</span></label>
				<label class="check-row"><input id="autopilot-include-chat" type="checkbox"><span>生成草稿时读取最近聊天上下文</span></label>
				<label class="check-row"><input id="autopilot-force" type="checkbox"><span>强制重新拉取并重新评估所有候选人</span></label>
			</div>
			<button class="button primary wide" id="autopilot-run-button">运行全职位 Autopilot</button>
			<div id="autopilot-status" class="autopilot-status">正在读取最近一次运行状态…</div>
			<div id="autopilot-result" class="autopilot-result hidden"></div>
		</article>
	`);

	function numberValue(selector, fallback) {
		const value = Number($(selector)?.value);
		return Number.isFinite(value) ? value : fallback;
	}

	async function loadAutopilotStatus() {
		const node = $("#autopilot-status");
		if (!node) return;
		try {
			const status = await api("/api/autopilot/status");
			const lastRun = status.last_run;
			if (!lastRun) {
				node.textContent = `尚未运行 · 已跟踪 ${status.tracked_candidates || 0} 位候选人`;
				return;
			}
			const totals = lastRun.summary?.totals || {};
			node.textContent = `最近运行 ${formatDate(lastRun.finished_at)} · 职位 ${totals.jobs_processed || 0} · 新评估 ${totals.evaluated || 0} · 增量跳过 ${totals.freshness_skipped || 0}`;
		} catch (error) {
			node.textContent = `Autopilot 状态读取失败：${error.message}`;
		}
	}

	function renderAutopilotResult(result) {
		const node = $("#autopilot-result");
		if (!node) return;
		const totals = result.totals || {};
		const jobs = Array.isArray(result.jobs) ? result.jobs : [];
		const unconfigured = Array.isArray(result.unconfigured_platform_jobs) ? result.unconfigured_platform_jobs : [];
		const profileSync = result.job_profile_sync || {};
		const profileUpdates = Array.isArray(profileSync.updated) ? profileSync.updated : [];
		const profileWarnings = Array.isArray(profileSync.warnings) ? profileSync.warnings : [];
		node.classList.remove("hidden");
		node.innerHTML = `
			<div class="autopilot-metrics">
				<div><span>处理职位</span><strong>${totals.jobs_processed || 0}</strong></div>
				<div><span>发现候选人</span><strong>${totals.candidates_discovered || 0}</strong></div>
				<div><span>新评估</span><strong>${totals.evaluated || 0}</strong></div>
				<div><span>增量跳过</span><strong>${totals.freshness_skipped || 0}</strong></div>
				<div><span>回复草稿</span><strong>${totals.reply_drafts || 0}</strong></div>
				<div><span>失败</span><strong>${totals.failed || 0}</strong></div>
			</div>
			${profileUpdates.length ? `<div class="autopilot-human-note"><strong>本轮更新 ${profileUpdates.length} 个 AI 岗位画像：</strong><br>${profileUpdates.slice(0, 8).map(item => `${escapeHtml(item.job_key || item.job_id || "岗位")} · ${item.reason === "jd_changed" ? "BOSS JD 已变化，评分规则已重建" : "首次生成岗位画像"}`).join("<br>")}</div>` : ""}
			${profileWarnings.length ? `<div class="autopilot-warning"><strong>${profileWarnings.length} 个岗位画像需要关注：</strong><br>${profileWarnings.slice(0, 8).map(item => `${escapeHtml(item.job_key || item.job_id || "岗位")} · ${escapeHtml(item.warning || "岗位画像未更新")}`).join("<br>")}</div>` : ""}
			${result.catalog_warning ? `<div class="autopilot-warning">${escapeHtml(result.catalog_warning)}</div>` : ""}
			<div class="autopilot-job-list">
				${jobs.map(job => `<div class="autopilot-job-row"><div><strong>${escapeHtml(job.title || job.job_key || "岗位")}</strong><span>${escapeHtml(job.job_key || "")} · ${escapeHtml(job.job_id || "")}</span></div><div><span>发现 ${job.discovered_count || 0}</span><span>评估 ${job.evaluated_count || 0}</span><span>跳过 ${job.freshness_skipped_count || 0}</span><span>草稿 ${job.reply_draft_count || 0}</span><span class="${job.failed_count ? "risk-text" : ""}">失败 ${job.failed_count || 0}</span></div></div>`).join("") || '<div class="empty-state small">本轮没有可处理职位</div>'}
			</div>
			${unconfigured.length ? `<div class="autopilot-warning"><strong>${unconfigured.length} 个 BOSS 职位未能自动配置：</strong><br>${unconfigured.slice(0, 8).map(job => `${escapeHtml(job.title || job.job_id || "职位")} ${job.error ? `· ${escapeHtml(job.error)}` : ""}`).join("<br>")}</div>` : ""}
			<div class="autopilot-human-note">AI 结果仅进入本地排序、草稿和人工审核流程；本轮发送消息：${result.messages_sent || 0}。</div>
		`;
		loadAutopilotStatus();
	}

	async function runAutopilot() {
		if (state.bootstrap?.operating_mode !== "research") {
			toast("请先在设置中切换到 Research Mode", "error");
			return;
		}
		if (!state.bootstrap?.auth?.logged_in) {
			toast("请先完成 BOSS 登录", "error");
			return;
		}
		if (!state.bootstrap?.ai?.configured) {
			toast("请先配置 AI 服务", "error");
			return;
		}
		const button = $("#autopilot-run-button");
		button.disabled = true;
		button.textContent = "正在启动…";
		try {
			const task = await api("/api/autopilot/run", {
				method: "POST",
				body: JSON.stringify({
					max_pages: numberValue("#autopilot-max-pages", 30),
					max_candidates_per_job: numberValue("#autopilot-max-candidates", 2000),
					refresh_seen_hours: numberValue("#autopilot-refresh-hours", 24),
					top: 50,
					draft_top: numberValue("#autopilot-draft-top", 10),
					include_chat: Boolean($("#autopilot-include-chat")?.checked),
					force: Boolean($("#autopilot-force")?.checked),
					auto_configure: Boolean($("#autopilot-auto-configure")?.checked),
				}),
			});
			state.taskCallbacks.set(task.id, renderAutopilotResult);
			watchTask(task.id);
			toast("全职位 Autopilot 已启动");
		} catch (error) {
			toast(error.message, "error");
		} finally {
			button.disabled = false;
			button.textContent = "运行全职位 Autopilot";
		}
	}

	$("#autopilot-run-button").addEventListener("click", runAutopilot);
	document.addEventListener("click", async event => {
		const target = event.target.closest("[data-task-id]");
		if (!target?.dataset.taskId) return;
		try {
			const task = await api(`/api/tasks/${encodeURIComponent(target.dataset.taskId)}`);
			if (task.kind === "autopilot" && task.result) {
				renderAutopilotResult(task.result);
				setView("screening");
			}
		} catch {
			// The base task-history handler owns user-facing request errors.
		}
	});
	loadAutopilotStatus();
})();
