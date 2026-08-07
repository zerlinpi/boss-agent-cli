(() => {
	function ensureTaskCancelButton() {
		const banner = document.querySelector("#task-banner");
		if (!banner) return null;
		let button = document.querySelector("#task-cancel-button");
		if (button) return button;
		button = document.createElement("button");
		button.id = "task-cancel-button";
		button.type = "button";
		button.className = "button ghost compact-button";
		button.textContent = "取消任务";
		button.hidden = true;
		banner.append(button);
		button.addEventListener("click", async () => {
			const taskId = state.activeTask;
			if (!taskId) return;
			button.disabled = true;
			button.textContent = "正在取消…";
			try {
				const task = await api(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, {
					method: "POST",
					body: "{}",
				});
				renderTask(task);
				toast(
					task.status === "cancelling" ? "取消请求已提交，等待当前操作返回" : "任务已取消",
				);
			} catch (error) {
				toast(error.message || "取消任务失败", "error");
			} finally {
				button.disabled = false;
				button.textContent = "取消任务";
			}
		});
		return button;
	}

	const originalRenderTask = renderTask;
	renderTask = function renderTaskWithCancel(task) {
		originalRenderTask(task);
		const button = ensureTaskCancelButton();
		if (button) button.hidden = !["queued", "running"].includes(task?.status);
	};

	const originalApplyBootstrap = applyBootstrap;
	applyBootstrap = function applyBootstrapWithCancellingTask() {
		originalApplyBootstrap();
		const cancelling = state.tasks.find(task => task.status === "cancelling");
		if (cancelling && cancelling.id !== state.activeTask) watchTask(cancelling.id);
	};

	ensureTaskCancelButton();
})();
