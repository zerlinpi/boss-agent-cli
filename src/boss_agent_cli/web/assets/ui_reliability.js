(() => {
	const MAX_RECRUITER_BATCH_BYTES = 40 * 1024 * 1024;
	const MAX_RECRUITER_JSON_CHARS = 500000;
	const MAX_RECRUITER_FILES = 100;
	const MAX_RECRUITER_FILE_BYTES = 12 * 1024 * 1024;
	const MAX_TASK_POLL_FAILURES = 3;
	const MAX_CANDIDATE_DETAIL_CACHE = 100;
	const inFlightWrites = new Map();
	const taskPollers = new Map();
	let jobAnalysisGeneration = 0;
	let detailCacheJob = state.activeJob;

	const originalApi = api;
	api = function reliableApi(path, options = {}) {
		const method = String(options.method || "GET").toUpperCase();
		if (method === "GET" || method === "HEAD") return originalApi(path, options);
		const body = typeof options.body === "string" ? options.body : "";
		const key = `${method}\n${path}\n${body}`;
		const existing = inFlightWrites.get(key);
		if (existing) return existing;
		const request = Promise.resolve(originalApi(path, options)).finally(() => {
			if (inFlightWrites.get(key) === request) inFlightWrites.delete(key);
		});
		inFlightWrites.set(key, request);
		return request;
	};

	function latestWatchedTask(exclude = "") {
		const ids = [...taskPollers.keys()].filter(id => id !== exclude);
		return ids.length ? ids[ids.length - 1] : null;
	}

	async function renderWatchedTask(id) {
		if (!id) return;
		try {
			const task = await api(`/api/tasks/${encodeURIComponent(id)}`);
			if (state.activeTask === id) renderTask(task);
		} catch {
			// The next normal poll or activity refresh will surface a persistent problem.
		}
	}

	watchTask = function multiTaskWatch(id) {
		if (!id) return;
		state.activeTask = id;
		$("#task-banner").classList.remove("hidden");
		const existing = taskPollers.get(id);
		if (existing) {
			void renderWatchedTask(id);
			return;
		}

		const entry = { timer: null, polling: false, failures: 0 };
		taskPollers.set(id, entry);
		const finish = async task => {
			if (entry.timer) clearInterval(entry.timer);
			taskPollers.delete(id);
			const callback = state.taskCallbacks.get(id);
			state.taskCallbacks.delete(id);

			if (task.status === "completed") {
				if (callback) {
					try { callback(task.result || {}); }
					catch (error) { toast(error.message || "任务完成回调执行失败", "error"); }
				}
				if (["screen-local", "screen-boss"].includes(task.kind)) renderScreenResult(task.result || {});
				toast("任务执行完成");
			} else {
				toast(task.error?.message || "任务执行失败", "error");
			}

			try { await bootstrap(); }
			catch { /* bootstrap already reports its own error */ }

			if (state.activeTask === id) {
				const next = latestWatchedTask(id);
				state.activeTask = next;
				if (next) {
					await renderWatchedTask(next);
				} else {
					setTimeout(() => {
						if (!state.activeTask && taskPollers.size === 0) $("#task-banner").classList.add("hidden");
					}, 2500);
				}
			}
		};

		const poll = async () => {
			if (entry.polling) return;
			entry.polling = true;
			try {
				const task = await api(`/api/tasks/${encodeURIComponent(id)}`);
				entry.failures = 0;
				if (state.activeTask === id) renderTask(task);
				if (["completed", "failed"].includes(task.status)) await finish(task);
			} catch (error) {
				entry.failures += 1;
				if (entry.failures < MAX_TASK_POLL_FAILURES) return;
				if (entry.timer) clearInterval(entry.timer);
				taskPollers.delete(id);
				state.taskCallbacks.delete(id);
				if (state.activeTask === id) {
					state.activeTask = latestWatchedTask(id);
					if (!state.activeTask) $("#task-banner").classList.add("hidden");
				}
				toast(error.message || "任务状态连续读取失败，已停止轮询", "error");
			} finally {
				entry.polling = false;
			}
		};

		entry.timer = setInterval(() => { void poll(); }, 1000);
		void poll();
	};
	state.pollTimer = null;

	function pruneCandidateDetailCache(activeId = "") {
		if (activeId && state.candidateDetails.has(activeId)) {
			const value = state.candidateDetails.get(activeId);
			state.candidateDetails.delete(activeId);
			state.candidateDetails.set(activeId, value);
		}
		while (state.candidateDetails.size > MAX_CANDIDATE_DETAIL_CACHE) {
			const oldest = state.candidateDetails.keys().next().value;
			if (oldest === undefined) break;
			state.candidateDetails.delete(oldest);
		}
	}

	const originalApplyBootstrap = applyBootstrap;
	applyBootstrap = function reliableApplyBootstrap() {
		if (detailCacheJob !== state.activeJob) {
			state.candidateDetails.clear();
			detailCacheJob = state.activeJob;
		}
		return originalApplyBootstrap();
	};

	const originalSelectJob = selectJob;
	selectJob = function reliableSelectJob(key) {
		if (key !== state.activeJob) {
			state.candidateDetails.clear();
			detailCacheJob = key;
		}
		return originalSelectJob(key);
	};

	const originalOpenCandidate = openCandidate;
	openCandidate = async function boundedOpenCandidate(id) {
		await originalOpenCandidate(id);
		pruneCandidateDetailCache(id);
	};

	async function safeAnalyzeJob() {
		const form = $("#job-form");
		const jdText = form.elements.jd_text.value.trim();
		if (jdText.length < 30) { toast("请先填写完整岗位 JD", "error"); return; }
		const jobKey = form.elements.job_key.value.trim();
		const generation = ++jobAnalysisGeneration;
		const button = $("#analyze-jd-button");
		button.disabled = true;
		button.textContent = "正在提交分析…";
		try {
			const task = await api("/api/jobs/analyze", {
				method: "POST",
				body: JSON.stringify({ jd_text: jdText }),
			});
			state.taskCallbacks.set(task.id, result => {
				const sameRequest = generation === jobAnalysisGeneration;
				const sameJob = form.elements.job_key.value.trim() === jobKey;
				const sameJd = form.elements.jd_text.value.trim() === jdText;
				const editorOpen = !$("#job-editor").classList.contains("hidden");
				if (!sameRequest || !sameJob || !sameJd || !editorOpen) {
					toast("岗位内容已在分析期间发生变化，本次 AI 结果未覆盖当前表单", "error");
					return;
				}
				if (result.title && !form.elements.title.value.trim()) form.elements.title.value = result.title;
				form.elements.rubric.value = JSON.stringify(result.rubric || {}, null, 2);
				const panel = $("#job-analysis");
				panel.classList.remove("hidden");
				panel.innerHTML = `<strong>岗位画像</strong><p>${escapeHtml(result.persona_summary || "已生成评分规则")}</p>${Array.isArray(result.suggested_questions) && result.suggested_questions.length ? `<div class="chip-list">${result.suggested_questions.map(item => `<span class="chip">${escapeHtml(item)}</span>`).join("")}</div>` : ""}`;
			});
			watchTask(task.id);
			toast("岗位分析任务已启动");
		} catch (error) {
			toast(error.message, "error");
		} finally {
			button.disabled = false;
			button.textContent = "AI 分析 JD";
		}
	}

	async function safeCopy(text) {
		if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
			try {
				await navigator.clipboard.writeText(text);
				return true;
			} catch {
				// Fall through to the legacy selection based copy path.
			}
		}
		const area = document.createElement("textarea");
		area.value = text;
		area.setAttribute("readonly", "");
		area.style.position = "fixed";
		area.style.opacity = "0";
		area.style.pointerEvents = "none";
		document.body.append(area);
		area.focus();
		area.select();
		let copied = false;
		try { copied = document.execCommand("copy"); }
		catch { copied = false; }
		area.remove();
		return copied;
	}

	const uploadHint = document.querySelector("#resume-drop small");
	if (uploadHint) {
		uploadHint.textContent = "单文件最大 12 MB，单次最多 100 份 / 40 MB；PDF 最多 100 页";
	}

	const originalFileToDocument = fileToDocument;
	fileToDocument = async function boundedFileToDocument(file) {
		if (file.name.toLowerCase().endsWith(".json")) {
			const text = await file.text();
			if (text.length > MAX_RECRUITER_JSON_CHARS) {
				throw new Error(`${file.name}: JSON 简历内容超过 500000 字符限制`);
			}
			try {
				const payload = JSON.parse(text);
				if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
					throw new Error("JSON 顶层必须是对象");
				}
				return { name: file.name, payload };
			} catch (error) {
				throw new Error(`${file.name}: ${error.message || "JSON 格式错误"}`);
			}
		}
		return originalFileToDocument(file);
	};

	updateFileSelection = function boundedFileSelection(files) {
		const allowed = [".json", ".txt", ".md", ".pdf", ".docx"];
		const selected = [];
		let total = 0;
		let skipped = 0;
		for (const file of [...files]) {
			if (selected.length >= MAX_RECRUITER_FILES) { skipped += 1; continue; }
			if (!allowed.some(extension => file.name.toLowerCase().endsWith(extension))) { skipped += 1; continue; }
			if (file.size > MAX_RECRUITER_FILE_BYTES) { skipped += 1; continue; }
			if (total + file.size > MAX_RECRUITER_BATCH_BYTES) { skipped += 1; continue; }
			selected.push(file);
			total += file.size;
		}
		state.selectedFiles = selected;
		$("#resume-file-summary").textContent = selected.length
			? `已选择 ${selected.length} 个文件，共 ${formatBytes(total)}`
			: "尚未选择文件";
		$("#resume-file-list").innerHTML = selected.slice(0, 8)
			.map(file => `<span class="file-chip">${escapeHtml(file.name)} <small>${formatBytes(file.size)}</small></span>`)
			.join("") + (selected.length > 8 ? `<span class="file-chip">另有 ${selected.length - 8} 份</span>` : "");
		if (skipped > 0 && typeof toast === "function") {
			toast(`有 ${skipped} 个文件因格式、数量或 40 MB 批次上限未加入`, "error");
		}
	};

	async function boundedScreenLocal() {
		if (!state.activeJob) { toast("请先创建并选择岗位", "error"); return; }
		if (!state.selectedFiles.length) { toast("请选择至少一份简历", "error"); return; }
		const button = $("#screen-local-button");
		button.disabled = true;
		try {
			const documents = [];
			for (let index = 0; index < state.selectedFiles.length; index += 1) {
				button.textContent = `正在读取文件 ${index + 1}/${state.selectedFiles.length}…`;
				documents.push(await fileToDocument(state.selectedFiles[index]));
			}
			button.textContent = "正在提交筛选任务…";
			const task = await api("/api/screen/local", {
				method: "POST",
				body: JSON.stringify({
					job_key: state.activeJob,
					documents,
					force: $("#local-force").checked,
				}),
			});
			watchTask(task.id);
			toast("本地简历筛选任务已启动");
		} catch (error) {
			toast(`读取简历失败：${error.message}`, "error");
		} finally {
			button.disabled = false;
			button.textContent = "开始本地筛选";
		}
	}

	document.addEventListener("click", async event => {
		const copyButton = event.target.closest("[data-copy-text]");
		if (copyButton) {
			// app.js also has a generic copy handler. Capture first and prevent that handler from
			// producing an unhandled rejection when Clipboard API permission is unavailable.
			event.preventDefault();
			event.stopImmediatePropagation();
			const copied = await safeCopy(copyButton.dataset.copyText || "");
			if (typeof toast === "function") {
				toast(copied ? "已复制到剪贴板" : "复制失败，请手动选择文本", copied ? "success" : "error");
			}
			return;
		}

		const analyzeButton = event.target.closest("#analyze-jd-button");
		if (analyzeButton) {
			event.preventDefault();
			event.stopImmediatePropagation();
			await safeAnalyzeJob();
			return;
		}

		const screenButton = event.target.closest("#screen-local-button");
		if (!screenButton) return;
		event.preventDefault();
		event.stopImmediatePropagation();
		await boundedScreenLocal();
	}, true);
})();
