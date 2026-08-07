(() => {
	const MAX_RECRUITER_BATCH_BYTES = 40 * 1024 * 1024;
	const MAX_RECRUITER_JSON_CHARS = 500000;
	const MAX_RECRUITER_FILES = 100;
	const MAX_RECRUITER_FILE_BYTES = 12 * 1024 * 1024;

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

		const screenButton = event.target.closest("#screen-local-button");
		if (!screenButton) return;
		event.preventDefault();
		event.stopImmediatePropagation();
		await boundedScreenLocal();
	}, true);
})();
