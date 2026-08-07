/* Local contacts stay available to recruiters but are excluded from AI scoring payloads. */
const baseRenderCandidateDrawerForContacts = renderCandidateDrawer;
renderCandidateDrawer = function renderCandidateDrawerWithContacts(record) {
    baseRenderCandidateDrawerForContacts(record);
    const contacts = record.contacts || {};
    const groups = [
        ["电话", contacts.phone || []],
        ["邮箱", contacts.email || []],
        ["微信", contacts.wechat || []],
        ["QQ", contacts.qq || []],
    ].filter(([, values]) => Array.isArray(values) && values.length);
    if (!groups.length) return;

    const section = document.createElement("section");
    section.className = "detail-section contact-retention-section";
    section.innerHTML = `<div class="contact-retention-head"><div><h3>联系方式</h3><p>仅保存在本机，用于人工联系；不参与 AI 评分或推荐。</p></div><span class="badge new">LOCAL ONLY</span></div><div class="contact-retention-list">${groups.map(([label, values]) => `
        <div class="contact-retention-row"><strong>${escapeHtml(label)}</strong><div>${values.map(value => `<button class="contact-value" type="button" data-copy-text="${escapeHtml(value)}" title="点击复制">${escapeHtml(value)}</button>`).join("")}</div></div>`).join("")}</div>`;

    const container = $("#drawer-content");
    const score = container?.querySelector(".detail-score");
    if (score) score.after(section);
    else container?.prepend(section);
};
