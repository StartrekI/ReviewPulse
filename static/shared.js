// Sidebar — Flask single-page version (counts hydrate after analysis)
window.RP_SIDEBAR = function(activeId) {
  const items = [
    { id: 'dashboard', label: 'Dashboard', href: '#', countId: 'side-count-dashboard',
      icon: '<rect x="2" y="2" width="5" height="6" rx="1.5" stroke="currentColor" stroke-width="1.4"/><rect x="9" y="2" width="5" height="3.5" rx="1.5" stroke="currentColor" stroke-width="1.4"/><rect x="2" y="10" width="5" height="4" rx="1.5" stroke="currentColor" stroke-width="1.4"/><rect x="9" y="7.5" width="5" height="6.5" rx="1.5" stroke="currentColor" stroke-width="1.4"/>' },
    { id: 'reviews', label: 'Reviews', href: '#explorer', countId: 'side-count-reviews',
      icon: '<path d="M3 4h10M3 8h10M3 12h6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>' },
    { id: 'trends', label: 'Trends', href: '#trend-card', countId: 'side-count-trends',
      icon: '<circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.4"/><path d="M8 5v3l2 1.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>' },
    { id: 'compare', label: 'Compare', href: '#', countId: null,
      icon: '<path d="M3 8c1.5-3 3-4.5 5-4.5s3.5 1.5 5 4.5c-1.5 3-3 4.5-5 4.5S4.5 11 3 8Z" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="8" r="1.5" stroke="currentColor" stroke-width="1.4"/>' },
    { id: 'collections', label: 'Collections', href: '#', countId: null,
      icon: '<path d="M2 6l6-3 6 3-6 3-6-3Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M2 10l6 3 6-3" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>' }
  ];

  return `
    <aside class="side">
      <a href="/" class="brand">
        <div class="brand-mark">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M2 9.5 L5 9.5 L6.5 5 L9.5 11 L11 8.5 L14 8.5" stroke="white" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <div>
          <div class="brand-name">ReviewPulse</div>
          <div class="brand-sub">Insight Engine</div>
        </div>
      </a>

      <div class="nav-section">Workspace</div>
      ${items.map(i => `
        <a href="${i.href}" class="nav-item ${i.id === activeId ? 'active' : ''}">
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none">${i.icon}</svg>
          ${i.label}
          ${i.countId ? `<span class="nav-count" id="${i.countId}"></span>` : ''}
        </a>
      `).join('')}

      <div class="nav-section">Status</div>
      <div class="nav-item" style="cursor:default;">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.4"/><path d="M8 4.5V8l2.5 1.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
        <span id="side-status-text" style="font-size:12px; color:var(--ink-3);">Idle — paste a URL</span>
      </div>

      <div class="side-foot" id="side-foot" style="opacity: 0.7;">
        <div class="avatar" id="side-avatar" style="background:linear-gradient(135deg, var(--accent), oklch(60% 0.2 290));">RP</div>
        <div>
          <div class="name" id="side-product-name">No product loaded</div>
          <div class="plan" id="side-product-meta">Paste a Flipkart URL above</div>
        </div>
      </div>
    </aside>
  `;
};

document.addEventListener('DOMContentLoaded', () => {
  const slot = document.querySelector('[data-sidebar]');
  if (slot) slot.outerHTML = window.RP_SIDEBAR(slot.getAttribute('data-sidebar'));
});
