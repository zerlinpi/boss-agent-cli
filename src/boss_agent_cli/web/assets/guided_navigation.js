(() => {
	const PRIMARY_VIEWS = ["dashboard", "screening", "pipeline", "replies", "settings"];

	function syncGuidedNavigationState() {
		$$(".nav-item[data-view]").forEach(item => {
			const index = PRIMARY_VIEWS.indexOf(item.dataset.view);
			if (index >= 0) item.setAttribute("aria-keyshortcuts", String(index + 1));
			else item.removeAttribute("aria-keyshortcuts");
			if (item.classList.contains("active")) item.setAttribute("aria-current", "page");
			else item.removeAttribute("aria-current");
		});
		$$("[data-pipeline-mode]").forEach(button => {
			button.setAttribute("aria-pressed", String(button.classList.contains("active")));
		});
	}

	document.addEventListener("keydown", event => {
		if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
		if (event.target.closest?.('input,textarea,select,[contenteditable="true"]')) return;
		const index = Number(event.key) - 1;
		if (index < 0 || index >= PRIMARY_VIEWS.length) return;
		event.preventDefault();
		event.stopImmediatePropagation();
		setView(PRIMARY_VIEWS[index]);
		setTimeout(syncGuidedNavigationState, 0);
	}, true);

	const nav = $(".nav-list");
	if (nav) {
		new MutationObserver(syncGuidedNavigationState).observe(nav, {
			attributes: true,
			attributeFilter: ["class"],
			subtree: true,
		});
	}
	const pipelineModes = $("[data-pipeline-mode]")?.parentElement;
	if (pipelineModes) {
		new MutationObserver(syncGuidedNavigationState).observe(pipelineModes, {
			attributes: true,
			attributeFilter: ["class"],
			subtree: true,
		});
	}
	setTimeout(syncGuidedNavigationState, 0);
})();