(() => {
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

	document.addEventListener("click", async event => {
		const button = event.target.closest("[data-copy-text]");
		if (!button) return;
		// app.js also has a generic copy handler. Capture first and prevent that handler from
		// producing an unhandled rejection when Clipboard API permission is unavailable.
		event.preventDefault();
		event.stopImmediatePropagation();
		const copied = await safeCopy(button.dataset.copyText || "");
		if (typeof toast === "function") {
			toast(copied ? "已复制到剪贴板" : "复制失败，请手动选择文本", copied ? "success" : "error");
		}
	}, true);
})();
