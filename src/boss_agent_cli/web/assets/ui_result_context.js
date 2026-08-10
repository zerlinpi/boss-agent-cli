window.addEventListener("load", () => {
	const downstreamRenderScreenResult = renderScreenResult;
	renderScreenResult = function contextAwareScreenResult(result) {
		const resultJob = String(result?.job_key || "").trim();
		if (resultJob && state.activeJob && resultJob !== state.activeJob) {
			const job = state.jobs.find(item => item.job_key === resultJob);
			toast(`岗位“${job?.title || resultJob}”筛选已完成，可在任务与审计中查看结果。`);
			return;
		}
		return downstreamRenderScreenResult(result);
	};
});
