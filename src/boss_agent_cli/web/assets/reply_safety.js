/* Surface deterministic reply safety flags in the recruiter UI. */
function replySafetyLabel(flag) {
	return ({
		reply_too_long: '回复过长',
		protected_attribute: '涉及受保护属性',
		employment_promise: '包含录用承诺',
		contact_exposure: '包含联系方式',
	})[flag] || flag;
}

function replySafetyMarkup(draft) {
	const flags = Array.isArray(draft?.safety_flags) ? draft.safety_flags : [];
	if (!draft?.prohibited_content_detected && !flags.length) return '';
	return `<div class="reply-safety-warning"><strong>需要重点复核</strong><span>${flags.length ? flags.map(replySafetyLabel).map(escapeHtml).join(' · ') : '模型标记了潜在不合规内容'}</span></div>`;
}

const baseRenderReplies = renderReplies;
renderReplies = function renderRepliesWithSafety() {
	baseRenderReplies();
	$$('#reply-grid .reply-card').forEach((card, index) => {
		const warning = replySafetyMarkup(state.replies[index]?.draft);
		if (!warning || card.querySelector('.reply-safety-warning')) return;
		card.querySelector('.reply-text')?.insertAdjacentHTML('beforebegin', warning);
	});
};

generateReply = async function generateReplyWithSafety(id) {
	const button = $(`[data-action="generate-reply"][data-evaluation-id="${CSS.escape(id)}"]`);
	button.disabled = true;
	button.textContent = '生成中…';
	try {
		const record = await api('/api/replies', {
			method: 'POST',
			body: JSON.stringify({
				evaluation_id: id,
				conversation: $('#drawer-conversation').value,
				intent: $('#drawer-intent').value,
			}),
		});
		const draft = record.draft || {};
		const reply = draft.reply || '';
		$('#drawer-reply-output').innerHTML = `${replySafetyMarkup(draft)}<div class="reply-output">${escapeHtml(reply)}</div><button class="button ghost" data-copy-text="${escapeHtml(reply)}">复制草稿</button>`;
		toast(draft.prohibited_content_detected ? '草稿已生成，但包含需要重点复核的内容' : '回复草稿已生成', draft.prohibited_content_detected ? 'error' : 'success');
		loadReplies();
	} catch (error) { toast(error.message, 'error'); }
	finally { button.disabled = false; button.textContent = '生成草稿'; }
};
