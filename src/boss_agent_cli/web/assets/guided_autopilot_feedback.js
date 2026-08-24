(() => {
	let decorating = false;

	function metricMap(result) {
		const values = {};
		result.querySelectorAll(".autopilot-metrics > div").forEach(card => {
			const label = card.querySelector("span")?.textContent?.trim();
			const raw = card.querySelector("strong")?.textContent?.trim();
			if (!label) return;
			const value = Number.parseInt(raw || "0", 10);
			values[label] = Number.isFinite(value) ? value : 0;
		});
		return values;
	}

	function decorateAutopilotResult() {
		if (decorating) return;
		const result = $("#autopilot-result");
		if (!result || result.classList.contains("hidden") || !result.querySelector(".autopilot-metrics")) return;
		decorating = true;
		try {
			const metrics = metricMap(result);
			const evaluated = metrics["新评估"] || 0;
			const discovered = metrics["发现候选人"] || 0;
			const drafts = metrics["回复草稿"] || 0;
			const failed = metrics["失败"] || 0;

			let title = "本轮同步完成";
			let description = "可以继续人工复核候选人，AI 不会自动做最终招聘决定。";
			if (failed > 0) {
				title = `本轮完成，${failed} 项需要处理`;
				description = "成功结果已保留。先查看候选人，再检查下方失败职位和告警。";
			} else if (evaluated > 0) {
				title = `新增 ${evaluated} 位候选人已进入人工复核`;
				description = drafts > 0
					? `已生成 ${drafts} 份回复草稿；建议先核对候选人证据，再人工审核草稿。`
					: "建议先核对候选人证据、评分理由和待确认项。";
			} else if (discovered > 0) {
				title = "已同步最新投递，本轮没有新的评估";
				description = "发现的候选人可能已处理或仍在复查间隔内，无需重复评估。";
			} else {
				title = "本轮没有发现新的候选人";
				description = "保持增量模式即可；下次有新投递时再次运行 Autopilot。";
			}

			const summaryKey = `${evaluated}|${discovered}|${drafts}|${failed}`;
			let header = result.querySelector(".autopilot-result-heading");
			if (header?.dataset.summaryKey === summaryKey) return;
			if (!header) {
				header = document.createElement("div");
				header.className = "autopilot-result-heading";
				result.prepend(header);
			}
			header.dataset.summaryKey = summaryKey;
			header.innerHTML = `
				<div>
					<p class="eyebrow">RUN COMPLETE</p>
					<h4>${escapeHtml(title)}</h4>
					<p>${escapeHtml(description)}</p>
				</div>
				<div class="autopilot-result-actions">
					<button type="button" class="button primary compact-button" data-autopilot-result-action="candidates">查看候选人</button>
					${drafts > 0 ? '<button type="button" class="button ghost compact-button" data-autopilot-result-action="replies">审核回复草稿</button>' : ""}
					${failed > 0 ? '<button type="button" class="button ghost compact-button" data-autopilot-result-action="failures">查看失败项</button>' : ""}
				</div>
			`;
			result.setAttribute("role", "status");
			result.setAttribute("aria-live", "polite");
		} finally {
			decorating = false;
		}
	}

	function attachObserver() {
		const result = $("#autopilot-result");
		if (!result || result.dataset.feedbackObserved === "1") return false;
		result.dataset.feedbackObserved = "1";
		new MutationObserver(decorateAutopilotResult).observe(result, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
		decorateAutopilotResult();
		return true;
	}

	document.addEventListener("click", event => {
		const action = event.target.closest?.("[data-autopilot-result-action]")?.dataset.autopilotResultAction;
		if (!action) return;
		event.preventDefault();
		if (action === "candidates") {
			setView("pipeline");
			return;
		}
		if (action === "replies") {
			setView("replies");
			return;
		}
		if (action === "failures") {
			const target = $("#autopilot-result .autopilot-warning") || $("#autopilot-result .risk-text");
			target?.scrollIntoView({ behavior: "smooth", block: "center" });
		}
	});

	if (!attachObserver()) {
		const observer = new MutationObserver(() => {
			if (attachObserver()) observer.disconnect();
		});
		observer.observe(document.body, { childList: true, subtree: true });
	}
})();
