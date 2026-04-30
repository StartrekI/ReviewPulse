/* ReviewPulse v3 dashboard — data wiring for Claude Design layout.
 * Approach: each render function rewrites the innerHTML of one card region
 * with real values from the v2 API payload. Pixel layout is preserved by
 * matching the prototype's exact class names. */

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
let DATA = null;
let FILTER = { sentiment: 'all', feature: null, rating: null };
let TREND_RANGE = 12;   // months — toggled by the 12M / 6M / 3M buttons

// Initial state — empty until first analysis succeeds
document.body.dataset.state = 'empty';

const fmtPct = (n) => Math.round(n) + '%';
const fmtNet = (n) => (n > 0 ? '+' : '') + Math.round(n);
const escape = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// Icon library — keyed by icon name returned by category taxonomy.
// Filled in lazily from DATA.category.aspect_icons (server provides icon NAME),
// and translated via this map at render time.
const ICON_PATHS = {
  speaker:    '<path d="M8 3 5 6H2v4h3l3 3V3Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M11 6c.7.7 1 1.4 1 2s-.3 1.3-1 2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
  battery:    '<rect x="2" y="5" width="11" height="6" rx="1.5" stroke="currentColor" stroke-width="1.4"/><rect x="13.5" y="6.5" width="1.5" height="3" rx=".5" fill="currentColor"/>',
  headphones: '<path d="M8 2a6 6 0 0 0-6 6v2h2v-2a4 4 0 0 1 8 0v2h2V8a6 6 0 0 0-6-6Z" stroke="currentColor" stroke-width="1.4"/><rect x="2" y="9" width="3" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="11" y="9" width="3" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/>',
  mic:        '<rect x="6" y="2" width="4" height="8" rx="2" stroke="currentColor" stroke-width="1.4"/><path d="M3 8a5 5 0 0 0 10 0M8 13v2M5.5 15h5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
  diamond:    '<path d="m2 6 6-3 6 3-6 3-6-3Zm0 4 6 3 6-3" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
  phone:      '<rect x="3" y="2" width="10" height="12" rx="2" stroke="currentColor" stroke-width="1.4"/><path d="M7 11h2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
  tap:        '<circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.4"/>',
  rupee:      '<path d="M4 3h8M4 6h8M5 3c3 0 4 3 0 4M5 7l5 6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
  camera:     '<rect x="2" y="5" width="12" height="9" rx="1.5" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="9.5" r="2.5" stroke="currentColor" stroke-width="1.4"/><path d="M5 5l1-2h4l1 2" stroke="currentColor" stroke-width="1.4"/>',
  monitor:    '<rect x="2" y="3" width="12" height="8" rx="1.5" stroke="currentColor" stroke-width="1.4"/><path d="M5 14h6M8 11v3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
  cpu:        '<rect x="3" y="3" width="10" height="10" rx="1.5" stroke="currentColor" stroke-width="1.4"/><rect x="6" y="6" width="4" height="4" stroke="currentColor" stroke-width="1.4"/>',
  bed:        '<path d="M2 10v3M14 10v3M2 10h12M3 10V8a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
  ruler:      '<path d="M3 8h10v3H3zM5 8v2M7 8v3M9 8v2M11 8v3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
  clock:      '<circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.4"/><path d="M8 5v3l2 1" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
  tv:         '<rect x="2" y="3" width="12" height="9" rx="1.5" stroke="currentColor" stroke-width="1.4"/><path d="M5 14h6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
  pot:        '<path d="M3 7h10v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" stroke="currentColor" stroke-width="1.4"/>',
  shoe:       '<path d="M2 11c1-3 3-3 5-3l3 1c1 0 1 1 1 2l1 1h1v2H2v-3Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
  shirt:      '<path d="M3 5l3-2 2 1 2-1 3 2-1 3h-1v6H4V8H3l1-3Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
  bag:        '<path d="M3 5h10l1 9H2l1-9Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M5 5V4a3 3 0 0 1 6 0v1" stroke="currentColor" stroke-width="1.4"/>',
  drop:       '<path d="M8 2l4 6c1 2 0 5-2 6s-5 1-6-1-1-3 0-5l4-6Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
  spark:      '<path d="M8 2v4M8 10v4M2 8h4M10 8h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
  shield:     '<path d="M8 2 14 4v4c0 3-2 5-6 7-4-2-6-4-6-7V4l6-2Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
  wifi:       '<path d="M2 6.5C4 5 6 4 8 4s4 1 6 2.5M4 9c1-1 2.5-2 4-2s3 1 4 2M6.5 11.5c.5-.5 1-.7 1.5-.7s1 .2 1.5.7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><circle cx="8" cy="13.5" r="1" fill="currentColor"/>',
  scale:      '<path d="M2 13h12M5 13l1-7h4l1 7M6 4h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
};
const aspectLabel = (key) => (DATA?.category?.aspect_labels?.[key]) || key;
const aspectIcon  = (key) => ICON_PATHS[(DATA?.category?.aspect_icons?.[key]) || 'spark'] || ICON_PATHS.spark;

/* ── URL submission ─────────────────────────────────────────── */
$('#url-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const url = $('#url-input').value.trim();
  if (!url || !url.includes('flipkart.com')) {
    alert('Please paste a valid Flipkart product URL.');
    return;
  }
  showLoader();
  try {
    const res = await fetch('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Analysis failed');
    DATA = data;
    finishLoaderSteps();
    setTimeout(() => {
      hideLoader();
      document.body.dataset.state = 'ready';
      renderAll();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }, 400);
  } catch (err) {
    hideLoader();
    alert(err.message);
  }
});

$('#demo-dismiss')?.addEventListener('click', () => { $('#demo-banner').hidden = true; });

/* ── Loader ─────────────────────────────────────────────────── */
const STEP_LABELS = {
  scrape:  'Fetching product page + scraping reviews from Flipkart…',
  enrich:  'Computing per-review sentiment…',
  aspects: 'Aspect-based sentiment analysis…',
  cluster: 'Clustering complaint themes…',
  render:  'Rendering dashboard…',
};
let stepTimer = null;

function showLoader() {
  $('#rp-loader').hidden = false;
  $$('.rp-step').forEach((el) => { el.classList.remove('active', 'done'); });
  $('.rp-step[data-step="scrape"]').classList.add('active');
  $('#rp-loader-text').textContent = STEP_LABELS.scrape;

  // Scrape is the slow step (~30-60s for full Flipkart paginate). Hold it
  // visibly active and show an elapsed-seconds counter so the user sees
  // progress. Other steps cycle quickly once finishLoaderSteps fires.
  const start = Date.now();
  stepTimer = setInterval(() => {
    const sec = Math.floor((Date.now() - start) / 1000);
    $('#rp-loader-text').textContent = `${STEP_LABELS.scrape} (${sec}s elapsed)`;
  }, 1000);
}

function finishLoaderSteps() {
  clearInterval(stepTimer);
  // Quickly walk through the analysis steps now that the API has returned.
  const remaining = ['enrich', 'aspects', 'cluster'];
  $(`.rp-step[data-step="scrape"]`).classList.remove('active');
  $(`.rp-step[data-step="scrape"]`).classList.add('done');
  let i = 0;
  $(`.rp-step[data-step="${remaining[i]}"]`).classList.add('active');
  $('#rp-loader-text').textContent = STEP_LABELS[remaining[i]];
  const t = setInterval(() => {
    $(`.rp-step[data-step="${remaining[i]}"]`).classList.remove('active');
    $(`.rp-step[data-step="${remaining[i]}"]`).classList.add('done');
    i += 1;
    if (i >= remaining.length) {
      clearInterval(t);
      $('.rp-step[data-step="render"]').classList.add('active');
      $('#rp-loader-text').textContent = STEP_LABELS.render;
    } else {
      $(`.rp-step[data-step="${remaining[i]}"]`).classList.add('active');
      $('#rp-loader-text').textContent = STEP_LABELS[remaining[i]];
    }
  }, 250);
}

function hideLoader() {
  $('#rp-loader').hidden = true;
  clearInterval(stepTimer);
}

/* ── Render orchestration ──────────────────────────────────── */
/* Make the bottom row of "Deeper analysis" always sum to 12 cols.
 * Default layout: photo(7) + variant(5) | lp(6) + longevity(6).
 * Whichever cards are visible get their col-X spans rewritten so the row fills. */
function adjustGridLayout() {
  const isVis = (id) => {
    const el = document.getElementById(id);
    return el && el.style.display !== 'none';
  };
  const setCol = (id, n) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('col-3','col-4','col-5','col-6','col-7','col-8','col-12');
    el.classList.add('col-' + n);
  };
  // Bottom of "Deeper analysis" — photo / variant / lp now share rows
  const visible = ['photo-card', 'variant-card', 'lp-card'].filter(isVis);
  if (visible.length === 3) {
    setCol('photo-card', 6); setCol('variant-card', 6); setCol('lp-card', 12);
  } else if (visible.length === 2) {
    visible.forEach((id) => setCol(id, 6));
  } else if (visible.length === 1) {
    setCol(visible[0], 12);
  }
}

/* Clear all the prototype demo content from every dynamic card so a renderer
 * failure can't leave fake "Auralis Pro 2" data on screen. Every card shows
 * a 1-line "Loading…" until its renderer overwrites it. */
const DYNAMIC_CARD_IDS = [
  'product-card', 'sentiment-card', 'features-card', 'verdict-region',
  'clusters-card', 'spec-align-card', 'surprises-card',
  'spec-sheet-card', 'stardist-card', 'cb-card', 'forensics-card',
  'photo-card', 'variant-card', 'lp-card', 'usecase-card',
  'reviewer-profile-card', 'ai-card', 'explorer',
];
function clearAllCards() {
  DYNAMIC_CARD_IDS.forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.innerHTML = `<div style="padding:14px;font-size:11.5px;color:var(--ink-4);font-family:'Geist Mono',monospace;text-transform:uppercase;letter-spacing:0.06em;">Loading…</div>`;
      el.classList.remove('no-data-overlay');
    }
  });
}
/* Run a render fn safely — log errors but never break the chain. */
function safeRun(name, fn) {
  try { fn(); }
  catch (e) {
    console.error(`[render:${name}]`, e);
    const el = $(`#${name}-card`);
    if (el) el.innerHTML = `<div style="padding:14px;font-size:12px;color:var(--neg);">Render failed: ${e.message}</div>`;
  }
}

function renderAll() {
  const d = DATA;
  clearAllCards();
  safeRun('product',   () => renderProductCard(d));
  safeRun('keymeta',   () => renderKeyInsightsMeta(d));
  safeRun('sentiment', () => renderSentiment(d));
  safeRun('features',  () => renderFeatures(d));
  safeRun('verdict',   () => renderVerdict(d));
  safeRun('clusters',  () => renderClusters(d));
  safeRun('specalign', () => renderSpecAlignment(d));
  safeRun('surprises', () => renderSurprises(d));
  safeRun('specsheet', () => renderSpecSheet(d));
  safeRun('stardist',  () => renderStarDist(d));
  safeRun('cb',        () => renderCertifiedSplit(d));
  safeRun('forensics', () => renderForensics(d));
  safeRun('photo',     () => renderPhotos(d));
  safeRun('variant',   () => renderVariants(d));
  safeRun('lp',        () => renderLogisticsSplit(d));
  safeRun('usecase',   () => renderUseCases(d));
  safeRun('reviewer',  () => renderReviewerProfile(d));
  safeRun('ai',        () => renderAISummary(d));
  safeRun('explorer',  () => renderExplorer(d));
  // After all cards rendered, redistribute columns so visible cards
  // always fill 12-col rows (no gaps when photo/longevity are hidden)
  safeRun('layout',    () => adjustGridLayout());

  const product = (d.product?.title) || productNameFromUrl(d.meta.product_url);
  const cat = (d.category?.breadcrumb && d.category.breadcrumb.length)
    ? d.category.breadcrumb[d.category.breadcrumb.length - 1]
    : (d.category?.label || '');

  // Topbar crumb
  const cur = document.querySelector('.crumbs .cur');
  cur.innerHTML = `${escape(product.slice(0, 60))} <span class="mono" style="font-size:10.5px; color:var(--ink-3); background:var(--accent-soft); padding:2px 7px; border-radius:4px; margin-left:8px; text-transform:uppercase; letter-spacing:0.04em;">${escape(cat)}</span>`;

  // Hero meta — replace static "Engine v3.4" demo content
  const meta = $('#hero-meta-text');
  if (meta) {
    const when = new Date(d.meta.scraped_at).toLocaleTimeString(undefined,
      { hour: '2-digit', minute: '2-digit' });
    meta.innerHTML = `<b>${d.meta.review_count}</b> reviews scraped at ${when} · <b>${escape(cat || 'unknown category')}</b>`;
  }

  // Hide recent-pills demo row entirely — never useful without real history
  const recent = $('#recent-row');
  if (recent) recent.hidden = true;

  // Section-head buttons in "Key insights" — replace with real, contextual labels
  const ki = $('#key-insights-meta-buttons');
  if (ki) {
    const verifiedPct = d.aggregates.verified_pct || 0;
    const fmts = d.aggregates.date_format_breakdown || {};
    const dateRange = d.timeseries?.length
      ? `${d.timeseries[0].month} → ${d.timeseries[d.timeseries.length - 1].month}`
      : 'all time';
    ki.innerHTML = `
      <span class="btn sm" style="cursor:default;">${dateRange}</span>
      <span class="btn sm" style="cursor:default;">${verifiedPct}% verified</span>`;
  }

  // "Deeper analysis" category pill — was hardcoded "Flipkart-specific signals"
  const dcp = $('#deeper-cat-pill');
  if (dcp) dcp.textContent = cat ? `Category: ${cat}` : 'General';

  // Sidebar counts — hydrate from data
  const sc1 = $('#side-count-reviews');
  if (sc1) sc1.textContent = d.aggregates.total_reviews;
  const sc2 = $('#side-count-trends');
  if (sc2) sc2.textContent = (d.timeseries?.length || 0) + 'mo';
  const sc3 = $('#side-count-dashboard');
  if (sc3) sc3.textContent = '1';

  // Sidebar status footer — replace fake user
  const status = $('#side-status-text');
  if (status) status.textContent = 'Analysis complete';
  const sn = $('#side-product-name');
  if (sn) sn.textContent = (d.product?.brand || product.split(' ')[0] || 'Product').slice(0, 24);
  const sm = $('#side-product-meta');
  if (sm) sm.textContent = `${d.aggregates.total_reviews} reviews · ${d.aggregates.average_rating.toFixed(1)}★`;
  const av = $('#side-avatar');
  if (av && d.product?.brand) {
    av.textContent = d.product.brand.slice(0, 2).toUpperCase();
  } else if (av) {
    av.textContent = product.slice(0, 2).toUpperCase();
  }
  const sf = $('#side-foot');
  if (sf) sf.style.opacity = '1';
}

function productNameFromUrl(url) {
  try {
    const path = new URL(url).pathname.split('/')[1] || '';
    const words = path.split('-').filter((w) => w && !w.match(/^itm/));
    return words.slice(0, 8).map((w) => w[0].toUpperCase() + w.slice(1)).join(' ') || 'Product';
  } catch { return 'Product'; }
}

/* ── Product overview card ─────────────────────────────────── */
function renderProductCard(d) {
  const a = d.aggregates;
  const p = d.product || {};
  const total = a.total_reviews;
  const avg = a.average_rating;
  const pos = a.sentiment_distribution.positive || 0;
  const neg = a.sentiment_distribution.negative || 0;
  const neu = a.sentiment_distribution.neutral || 0;
  const posPct = Math.round(pos / total * 100);
  const negPct = Math.round(neg / total * 100);
  const neuPct = Math.round(neu / total * 100);
  const net = posPct - negPct;
  const trust = d.trust || { score: 7.0, risk: 'Low fake-review risk' };

  // Use real product data when available; fall back to URL-derived
  const productName = p.title || productNameFromUrl(d.meta.product_url);
  const brand = p.brand || '';
  const stars = renderStars(p.rating?.rating || avg);
  const urlShort = d.meta.product_url.replace(/^https?:\/\/(www\.)?/, '').slice(0, 60);
  const heroImg = p.images?.[0];

  // Pricing
  const finalPrice = p.pricing?.final_price;
  const mrp = p.pricing?.mrp;
  const discount = p.pricing?.discount_pct;
  const priceLine = finalPrice
    ? `<div style="margin-top:8px; display:flex; align-items:baseline; gap:10px;">
         <span style="font-size:24px; font-weight:600; letter-spacing:-0.02em;">₹${finalPrice.toLocaleString('en-IN')}</span>
         ${mrp ? `<span style="color:var(--ink-3); text-decoration:line-through; font-size:13px;">₹${mrp.toLocaleString('en-IN')}</span>` : ''}
         ${discount ? `<span style="color:var(--pos); font-size:12px; font-weight:600;">${discount}% off</span>` : ''}
       </div>` : '';

  $('#product-card').innerHTML = `
    <div class="product-img" style="${heroImg ? `background-image:url('${escape(heroImg)}'); background-size:cover; background-position:center;` : ''}">
      ${!heroImg ? '<span>product shot</span>' : ''}
    </div>
    <div class="product-meta">
      <div class="brand-line">${escape(brand || 'Flipkart')}</div>
      <h2>${escape(productName)}</h2>
      <div class="product-rating">
        <div class="stars">${stars}</div>
        <span class="rating-num">${(p.rating?.rating || avg).toFixed(1)}</span>
        <span class="rating-count">· ${total} reviews analyzed${p.rating?.ratings_count ? ` · ${p.rating.ratings_count.toLocaleString('en-IN')} total ratings` : ''}</span>
      </div>
      ${priceLine}
      <div class="url-tag">
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none"><path d="M6.5 9.5 4 12a2 2 0 0 1-2.8-2.8L4 6.4M9.5 6.5 12 4a2 2 0 0 1 2.8 2.8L12 9.6" stroke="currentColor" stroke-width="1.5"/></svg>
        ${escape(urlShort)}
      </div>
    </div>
    <div class="stat-strip">
      <div class="stat-cell">
        <div class="stat-label">Sentiment</div>
        <div class="stat-val">${fmtNet(net)}</div>
        <div class="stat-sub"><span class="${avg >= 4 ? 'delta-pos' : 'delta-neg'}">${avg >= 4 ? '▲' : '▼'} ${avg.toFixed(1)}★</span> rating avg</div>
      </div>
      <div class="stat-cell">
        <div class="stat-label">Reviews analyzed</div>
        <div class="stat-val">${total}<span style="font-size:14px;color:var(--ink-3);font-weight:500;"> /${total}</span></div>
        <div class="stat-sub">complete</div>
      </div>
      <div class="stat-cell">
        <div class="stat-label">Pos · Neg</div>
        <div class="stat-val"><span style="color:var(--pos)">${posPct}%</span> <span style="color:var(--ink-4);font-weight:400;">·</span> <span style="color:var(--neg)">${negPct}%</span></div>
        <div class="stat-sub">${neuPct}% neutral</div>
      </div>
      <div class="stat-cell">
        <div class="stat-label">Trust score</div>
        <div class="stat-val">${trust.score.toFixed(1)}<span style="font-size:14px;color:var(--ink-3);font-weight:500;">/10</span></div>
        <div class="stat-sub"><span class="${trust.score >= 7 ? 'delta-pos' : 'delta-neg'}">●</span> ${escape(trust.risk)}</div>
      </div>
    </div>
  `;
}

/* ── Reviewer surprises ───────────────────────────────────── */
function renderSurprises(d) {
  const card = $('#surprises-card');
  const items = d.reviewer_surprises || [];
  if (!items.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = '';

  const upsides = items.filter((s) => s.tone === 'pos');
  const flaws   = items.filter((s) => s.tone === 'neg');

  const row = (s) => {
    const sign = s.tone === 'pos' ? '✓' : s.tone === 'neg' ? '✗' : '·';
    const iconSvg = ICON_PATHS[s.icon] || ICON_PATHS.spark;
    return `
      <div class="surprise-row tone-${s.tone}">
        <span class="surprise-ic"><svg width="13" height="13" viewBox="0 0 16 16" fill="none">${iconSvg}</svg></span>
        <div class="surprise-meta">
          <div class="surprise-label">${escape(s.aspect_label)}</div>
          <div class="surprise-sub">${s.mentions} mentions${s.rating ? ` · ${s.rating}★` : ''}</div>
        </div>
        <div class="surprise-net">${sign} ${fmtNet(s.net)}</div>
      </div>`;
  };

  card.innerHTML = `
    <div class="card-head">
      <div>
        <div class="card-title">Reviewer surprises</div>
        <div class="card-sub">Aspects buyers care about that the listing didn't mention</div>
      </div>
      <span class="card-action">${items.length} found</span>
    </div>
    ${upsides.length ? `
      <div class="surprise-section">
        <div class="surprise-section-head">
          <span class="surprise-pill pos">Hidden upsides</span>
          <span class="surprise-section-sub">Free wins not advertised</span>
        </div>
        ${upsides.slice(0, 4).map(row).join('')}
      </div>` : ''}
    ${flaws.length ? `
      <div class="surprise-section" style="margin-top:${upsides.length ? '12px' : '0'};">
        <div class="surprise-section-head">
          <span class="surprise-pill neg">Hidden flaws</span>
          <span class="surprise-section-sub">Issues seller didn't disclose</span>
        </div>
        ${flaws.slice(0, 4).map(row).join('')}
      </div>` : ''}
    ${!upsides.length && !flaws.length ? `
      <div style="padding:24px 14px; text-align:center; font-size:12px; color:var(--ink-4); font-family:'Geist Mono',monospace; text-transform:uppercase; letter-spacing:0.06em;">
        Listing covers everything reviewers discuss
      </div>` : ''}
  `;
}

/* ── Spec alignment (claim vs reality) ───────────────────── */
function renderSpecAlignment(d) {
  const card = $('#spec-align-card');
  const rows = d.spec_alignment || [];
  if (!rows.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = '';
  const compactVerdict = (v) => v === 'Lives up to spec' ? '✓ Match'
                              : v === 'Mixed reception'   ? '≈ Mixed'
                              : v === 'Underperforms claim' ? '✗ Miss'
                              : v;
  const html = rows.slice(0, 8).map((r) => `
    <div class="align-row">
      <div class="ar-main">
        <div class="ar-label">${escape(r.aspect_label)}</div>
        <div class="meta">${escape(r.spec_key)}: ${escape(String(r.spec_value).slice(0, 28))} · ${r.mentions} mentions</div>
      </div>
      <div class="net ${r.tone}">${fmtNet(r.net)}</div>
      <div class="verdict ${r.tone}">${escape(compactVerdict(r.verdict))}</div>
    </div>
  `).join('');
  card.innerHTML = `
    <div class="card-head">
      <div>
        <div class="card-title">Claim vs reality</div>
        <div class="card-sub">Spec promises matched against review sentiment</div>
      </div>
    </div>
    ${html}
  `;
}

/* ── Spec sheet ───────────────────────────────────────────── */
function renderSpecSheet(d) {
  const card = $('#spec-sheet-card');
  const specs = d.product?.specs || {};
  const flat = [];
  for (const grp of Object.values(specs)) {
    for (const [k, v] of Object.entries(grp)) {
      if (v && String(v).trim()) flat.push([k, String(v).trim()]);
    }
  }
  if (!flat.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = '';

  // Skip overly-long values (importer addresses) — show them last
  const isLong = (v) => v.length > 80;
  const short = flat.filter(([, v]) => !isLong(v));
  const long  = flat.filter(([, v]) => isLong(v));

  const halfA = short.slice(0, Math.ceil(short.length / 2));
  const halfB = short.slice(Math.ceil(short.length / 2));

  const renderHalf = (rows) => rows.map(([k, v]) => `
    <div class="spec-row">
      <span class="spec-key">${escape(k)}</span>
      <span class="spec-val">${escape(v)}</span>
    </div>`).join('');

  card.innerHTML = `
    <div class="card-head">
      <div>
        <div class="card-title">Full specifications</div>
        <div class="card-sub">${flat.length} attributes scraped from the product page</div>
      </div>
      <span class="card-action">View on Flipkart ↗</span>
    </div>
    <div class="spec-table">${renderHalf(halfA)}${renderHalf(halfB)}</div>
    ${long.length ? `<details style="margin-top:10px;font-size:12px;color:var(--ink-3);"><summary style="cursor:pointer;padding:6px 0;">+ ${long.length} long attributes (warranty, manufacturer)</summary>
       <div style="margin-top:6px; display:flex; flex-direction:column; gap:6px;">
         ${long.map(([k, v]) => `<div><b style="color:var(--ink-2);">${escape(k)}:</b> ${escape(v)}</div>`).join('')}
       </div>
     </details>` : ''}
  `;
}

function renderStars(rating) {
  const filled = Math.round(rating);
  let out = '';
  for (let i = 0; i < 5; i++) {
    out += `<svg ${i >= filled ? 'class="empty"' : ''} width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1.5l1.9 4 4.4.6-3.2 3.1.8 4.4L8 11.5 4.1 13.6l.8-4.4-3.2-3.1 4.4-.6L8 1.5Z"/></svg>`;
  }
  return out;
}

function renderKeyInsightsMeta(d) {
  const ago = '· just now';
  $('#key-insights-meta').textContent = `Auto-extracted from ${d.meta.review_count} reviews ${ago}`;
}

/* ── Sentiment overview (donut) ────────────────────────────── */
function renderSentiment(d) {
  const a = d.aggregates;
  const total = a.total_reviews;
  const pos = a.sentiment_distribution.positive || 0;
  const neg = a.sentiment_distribution.negative || 0;
  const neu = a.sentiment_distribution.neutral || 0;
  const posPct = pos / total;
  const neuPct = neu / total;
  const negPct = neg / total;
  const net = Math.round((pos - neg) / total * 100);
  const C = 389.6;
  const posLen = posPct * C;
  const neuLen = neuPct * C;
  const negLen = negPct * C;

  const aspects = d.aspects || {};
  const aspectsByRating = Object.entries(aspects)
    .filter(([, v]) => v && v.mentions > 0)
    .sort((a, b) => (b[1].rating || 0) - (a[1].rating || 0));
  const top = aspectsByRating.slice(0, 2).map(([k]) => aspectLabel(k));
  const bot = aspectsByRating.slice(-2).reverse().map(([k]) => aspectLabel(k));
  const quote = top.length
    ? `Most users praise <b>${top.join('</b> and <b>')}</b>${bot.length ? `, but a vocal minority flag <b>${bot.join('</b> and <b>')}</b>.` : '.'}`
    : 'Sentiment analysis based on review text.';

  $('#sentiment-card').innerHTML = `
    <div class="card-head">
      <div>
        <div class="card-title">Sentiment overview</div>
        <div class="card-sub">Distribution across all reviews</div>
      </div>
      <div class="card-action">Details ↗</div>
    </div>
    <div class="donut-wrap">
      <div class="donut-center">
        <svg viewBox="0 0 160 160" width="160" height="160">
          <circle cx="80" cy="80" r="62" fill="none" stroke="var(--hair-2)" stroke-width="20"/>
          <circle cx="80" cy="80" r="62" fill="none" stroke="var(--pos)" stroke-width="20"
                  stroke-dasharray="${posLen.toFixed(1)} ${C}" transform="rotate(-90 80 80)"/>
          <circle cx="80" cy="80" r="62" fill="none" stroke="var(--neu)" stroke-width="20"
                  stroke-dasharray="${neuLen.toFixed(1)} ${C}" stroke-dashoffset="${(-posLen).toFixed(1)}" transform="rotate(-90 80 80)"/>
          <circle cx="80" cy="80" r="62" fill="none" stroke="var(--neg)" stroke-width="20"
                  stroke-dasharray="${negLen.toFixed(1)} ${C}" stroke-dashoffset="${(-(posLen + neuLen)).toFixed(1)}" transform="rotate(-90 80 80)"/>
          <circle cx="80" cy="80" r="48" fill="var(--surface)"/>
        </svg>
        <div class="donut-num">
          <div>
            <div class="big tnum">${fmtNet(net)}</div>
            <div class="lbl">net score</div>
          </div>
        </div>
      </div>
      <div class="legend">
        <div class="legend-row"><span class="legend-dot" style="background:var(--pos);"></span><span class="lbl">Positive</span><span class="pct">${Math.round(posPct * 100)}%</span></div>
        <div class="legend-row"><span class="legend-dot" style="background:var(--neu);"></span><span class="lbl">Neutral</span><span class="pct">${Math.round(neuPct * 100)}%</span></div>
        <div class="legend-row"><span class="legend-dot" style="background:var(--neg);"></span><span class="lbl">Negative</span><span class="pct">${Math.round(negPct * 100)}%</span></div>
        <div style="height:1px;background:var(--hair-2);margin:4px 0;"></div>
        <div class="legend-row" style="font-size:12px;color:var(--ink-3);"><span class="lbl">Sample size</span><span class="pct mono">n = ${total}</span></div>
      </div>
    </div>
    <div class="insight-quote">
      <div class="icon"><svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 2v2M8 12v2M2 8h2M12 8h2M4 4l1.5 1.5M10.5 10.5 12 12M4 12l1.5-1.5M10.5 5.5 12 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></div>
      <div>${quote}</div>
    </div>
  `;
}

/* ── Feature-wise bars ─────────────────────────────────────── */
function renderFeatures(d) {
  const aspects = d.aspects || {};
  const ranked = Object.entries(aspects)
    .filter(([, v]) => v && v.mentions > 0)
    .sort((a, b) => b[1].sentences - a[1].sentences)
    .slice(0, 6);

  const rows = ranked.map(([key, a]) => {
    const total = a.pos + a.neu + a.neg || 1;
    const pP = (a.pos / total * 100).toFixed(0);
    const nP = (a.neu / total * 100).toFixed(0);
    const gP = (a.neg / total * 100).toFixed(0);
    const net = Math.round((a.pos - a.neg) / total * 100);
    return `
      <div class="feat-row">
        <div class="feat-head">
          <div class="feat-name">
            <span class="ic"><svg width="12" height="12" viewBox="0 0 16 16" fill="none">${aspectIcon(key)}</svg></span>
            ${escape(aspectLabel(key))}
          </div>
          <div class="feat-meta"><b>${fmtNet(net)}</b> · ${a.sentences} mentions</div>
        </div>
        <div class="feat-bar">
          <div style="width:${pP}%;background:var(--pos);"></div>
          <div style="width:${nP}%;background:var(--neu);"></div>
          <div style="width:${gP}%;background:var(--neg);"></div>
        </div>
      </div>`;
  }).join('');

  $('#features-card').innerHTML = `
    <div class="card-head">
      <div>
        <div class="card-title">Feature-wise sentiment</div>
        <div class="card-sub">Aspects auto-mined from review text</div>
      </div>
      <div class="card-action">Compare ↗</div>
    </div>
    <div class="feat-list">${rows || '<div style="font-size:12px;color:var(--ink-3);">No aspect mentions found.</div>'}</div>
  `;
}

/* ── Verdict ───────────────────────────────────────────────── */
function renderVerdict(d) {
  const v = d.verdict || { decision: 'Mixed', condition: '', confidence: 50, points: [] };
  const ok = v.decision === 'Worth buying';
  const iconColor = ok ? 'var(--pos)' : v.decision === 'Skip' ? 'var(--neg)' : 'var(--neu)';
  const iconBg = ok ? 'var(--pos-soft)' : v.decision === 'Skip' ? 'var(--neg-soft)' : 'var(--neu-soft)';
  const iconPath = ok
    ? '<path d="M5 12.5 10 17.5 19 7.5" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
    : v.decision === 'Skip'
    ? '<path d="M6 6 18 18M18 6 6 18" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>'
    : '<path d="M6 12h12" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>';

  const points = (v.points || []).map((p) => `
    <div class="verdict-point">
      <span class="vp-dot ${p.ok ? 'ok' : 'no'}">
        ${p.ok
          ? '<svg width="8" height="8" viewBox="0 0 8 8"><path d="M1.5 4 3.2 5.7 6.5 2.4" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>'
          : '<svg width="8" height="8" viewBox="0 0 8 8"><path d="M2 2 6 6M6 2 2 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>'}
      </span>${escape(p.text)}
    </div>`).join('');

  $('#verdict-region').innerHTML = `
    <div class="verdict">
      <div class="verdict-head">Verdict</div>
      <div class="verdict-decision">
        <div class="verdict-icon" style="background:${iconBg};color:${iconColor};">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">${iconPath}</svg>
        </div>
        <div>
          <div class="verdict-text">${escape(v.decision)}</div>
          ${v.condition ? `<span class="verdict-cond">${escape(v.condition)}</span>` : ''}
        </div>
      </div>
      <div>
        <div class="conf-meta" style="margin-bottom:6px;"><span>Confidence</span><span><b>${v.confidence}%</b></span></div>
        <div class="conf-bar"><div style="width:${v.confidence}%;"></div></div>
      </div>
      <div class="verdict-points">${points}</div>
    </div>
  `;
}

/* ── Sentiment trend chart ─────────────────────────────────── */
function renderTrend(d, range = TREND_RANGE) {
  TREND_RANGE = range;
  const all = d.timeseries || [];
  const ts = all.slice(-range);
  if (!ts.length) {
    $('#trend-card').innerHTML = `<div class="card-head"><div><div class="card-title">Sentiment trend</div><div class="card-sub">No timeseries data</div></div></div>`;
    return;
  }

  const L = 40, R = 590, T = 30, B = 175;
  const xStep = (R - L) / (ts.length - 1 || 1);
  const yMin = -100, yMax = 100;
  const yMap = (v) => T + (1 - (v - yMin) / (yMax - yMin)) * (B - T);

  const netPath = ts.map((b, i) => {
    const v = (b.avg_sentiment || 0) * 100;
    return `${i === 0 ? 'M' : 'L'} ${(L + i * xStep).toFixed(1)} ${yMap(v).toFixed(1)}`;
  }).join(' ');
  const areaPath = ts.length > 1
    ? `${netPath} L ${(L + (ts.length - 1) * xStep).toFixed(1)} ${B} L ${L.toFixed(1)} ${B} Z`
    : '';

  const negPath = ts.map((b, i) => {
    const negPct = b.n ? -b.negative / b.n * 100 : 0;
    return `${i === 0 ? 'M' : 'L'} ${(L + i * xStep).toFixed(1)} ${yMap(negPct).toFixed(1)}`;
  }).join(' ');

  const maxVol = Math.max(...ts.map((b) => b.n));
  const bars = ts.map((b, i) => {
    const x = L + i * xStep - 5;
    const h = 6 + (b.n / maxVol * 18);
    const isMax = b.n === maxVol && maxVol > 5;
    return `<rect x="${x.toFixed(1)}" y="${(B + 3 - h).toFixed(1)}" width="10" height="${h.toFixed(1)}" fill="${isMax ? 'oklch(85% 0.04 18)' : 'var(--hair)'}"/>`;
  }).join('');

  // Drop labels in dense series so they don't overlap
  const labelEvery = ts.length > 18 ? 3 : ts.length > 8 ? 2 : 1;
  const xLabels = ts.map((b, i) => {
    if (i % labelEvery !== 0 && i !== ts.length - 1) return '';
    const [, m] = b.month.split('-');
    const mname = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][parseInt(m) - 1];
    return `<text x="${(L + i * xStep).toFixed(1)}" y="195">${mname}</text>`;
  }).join('');

  const lastTs = ts[ts.length - 1];
  const endX = L + (ts.length - 1) * xStep;
  const endY = yMap((lastTs.avg_sentiment || 0) * 100);

  // Tooltips: invisible hit-rects for each month
  const hits = ts.map((b, i) => {
    const x = L + i * xStep;
    const sentLabel = (b.avg_sentiment * 100).toFixed(0);
    const tip = `${b.month} · ${b.n} reviews · sentiment ${sentLabel >= 0 ? '+' : ''}${sentLabel} · avg ${b.avg_rating.toFixed(1)}★`;
    return `<rect x="${(x - xStep / 2).toFixed(1)}" y="${T}" width="${xStep.toFixed(1)}" height="${B - T}" fill="transparent" data-tip="${tip}" class="trend-hit"/>`;
  }).join('');

  // Range buttons — JS hooks them up after render
  const btn = (label, n) => {
    const active = range === n;
    return `<button class="btn sm trend-range-btn" data-range="${n}" style="${active ? 'background:var(--ink);color:white;border-color:var(--ink);' : ''}">${label}</button>`;
  };

  const months = ts.length > 0 ? ts.length : 0;
  const totalReviewsInRange = ts.reduce((a, b) => a + b.n, 0);

  $('#trend-card').innerHTML = `
    <div class="card-head">
      <div>
        <div class="card-title">Sentiment trend</div>
        <div class="card-sub">Monthly · last ${months} month${months === 1 ? '' : 's'} · ${totalReviewsInRange} reviews</div>
      </div>
      <div style="display:flex;gap:6px;" id="trend-range-buttons">
        ${btn('12M', 12)}${btn('6M', 6)}${btn('3M', 3)}
      </div>
    </div>
    <svg class="trend-svg" viewBox="0 0 600 215" preserveAspectRatio="none">
      <g stroke="var(--hair-2)" stroke-dasharray="2 4">
        <line x1="40" y1="30" x2="590" y2="30"/>
        <line x1="40" y1="80" x2="590" y2="80"/>
        <line x1="40" y1="130" x2="590" y2="130"/>
        <line x1="40" y1="170" x2="590" y2="170"/>
      </g>
      <g font-family="Geist Mono, monospace" font-size="9" fill="var(--ink-4)">
        <text x="32" y="33" text-anchor="end">+100</text>
        <text x="32" y="83" text-anchor="end">+50</text>
        <text x="32" y="133" text-anchor="end">0</text>
        <text x="32" y="173" text-anchor="end">−50</text>
      </g>
      <defs>
        <linearGradient id="posGrad2" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="oklch(55% 0.18 265)" stop-opacity=".22"/>
          <stop offset="100%" stop-color="oklch(55% 0.18 265)" stop-opacity="0"/>
        </linearGradient>
      </defs>
      ${areaPath ? `<path d="${areaPath}" fill="url(#posGrad2)"/>` : ''}
      <path d="${netPath}" fill="none" stroke="oklch(55% 0.18 265)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
      <path d="${negPath}" fill="none" stroke="var(--neg)" stroke-width="1.5" stroke-dasharray="3 3" stroke-linejoin="round"/>
      <g>${bars}</g>
      ${ts.map((b, i) => {
        const x = L + i * xStep;
        const y = yMap((b.avg_sentiment || 0) * 100);
        return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.5" fill="var(--accent)" opacity="0.8"/>`;
      }).join('')}
      <circle cx="${endX.toFixed(1)}" cy="${endY.toFixed(1)}" r="4" fill="var(--accent)" stroke="white" stroke-width="2"/>
      <g font-family="Geist Mono, monospace" font-size="9" fill="var(--ink-4)" text-anchor="middle">${xLabels}</g>
      ${hits}
    </svg>
    <div class="trend-legend">
      <span style="display:inline-flex;align-items:center;gap:6px;"><span style="width:14px;height:2px;background:var(--accent);display:inline-block;"></span> Net sentiment</span>
      <span style="display:inline-flex;align-items:center;gap:6px;"><span style="width:14px;height:2px;background:var(--neg);display:inline-block;border-top:1px dashed var(--neg);"></span> Negative volume</span>
      <span style="display:inline-flex;align-items:center;gap:6px;"><span style="width:8px;height:8px;background:var(--hair);display:inline-block;"></span> Review volume</span>
      <span style="margin-left:auto;color:var(--ink-2);"><b>${months} months</b> of data · peak ${maxVol} reviews</span>
    </div>
    <div id="trend-tooltip" class="trend-tooltip" hidden></div>
  `;

  // Wire up the 12M / 6M / 3M buttons (interactive re-render)
  $$('.trend-range-btn').forEach((b) => {
    b.addEventListener('click', () => {
      const n = parseInt(b.dataset.range, 10);
      renderTrend(d, n);
    });
  });

  // Wire up hover tooltips on the invisible hit-rects
  const tt = $('#trend-tooltip');
  const card = $('#trend-card');
  $$('.trend-hit').forEach((rect) => {
    rect.addEventListener('mouseenter', (e) => {
      tt.textContent = e.target.dataset.tip;
      tt.hidden = false;
    });
    rect.addEventListener('mousemove', (e) => {
      const cardBox = card.getBoundingClientRect();
      tt.style.left = (e.clientX - cardBox.left + 12) + 'px';
      tt.style.top  = (e.clientY - cardBox.top  + 12) + 'px';
    });
    rect.addEventListener('mouseleave', () => { tt.hidden = true; });
  });
}

/* ── Complaint clusters ───────────────────────────────────── */
function renderClusters(d) {
  const clusters = (d.clusters || []);
  if (!clusters.length) {
    $('#clusters-card').innerHTML = `
      <div class="card-head">
        <div>
          <div class="card-title">Top complaint clusters</div>
          <div class="card-sub">No recurring complaints detected</div>
        </div>
      </div>
      <div style="padding:30px 14px; text-align:center; font-size:12px; color:var(--ink-4); font-family:'Geist Mono',monospace; text-transform:uppercase; letter-spacing:0.06em;">
        Sample is too positive to surface clusters
      </div>`;
    return;
  }

  const totalMentions = clusters.reduce((a, c) => a + c.size, 0);

  const cards = clusters.map((c) => {
    const sevTone   = c.severity === 'critical' ? 'crit'
                    : c.severity === 'warning'  ? 'warn'
                    :                             'note';
    const trendCls  = c.trend_pct >  20 ? 'trend-up'
                    : c.trend_pct < -20 ? 'trend-down'
                    :                     'trend-flat';
    const iconSvg = ICON_PATHS[c.icon] || ICON_PATHS.spark;

    return `
      <div class="cluster cluster-${sevTone}">
        <div class="cluster-head">
          <span class="cluster-icon"><svg width="14" height="14" viewBox="0 0 16 16" fill="none">${iconSvg}</svg></span>
          <div class="cluster-title-block">
            <div class="cluster-label">${escape(c.label)}</div>
            <div class="cluster-cat">${escape(c.category)}</div>
          </div>
          <span class="cluster-sev sev-${sevTone}">${c.severity}</span>
        </div>

        <div class="cluster-stats">
          <div><span class="stat-num">${c.size}</span><span class="stat-lbl">mentions</span></div>
          <div><span class="stat-num">${c.avg_rating.toFixed(1)}<span style="font-size:11px;color:var(--ink-3);font-weight:400;"> ★</span></span><span class="stat-lbl">avg rating</span></div>
          <div><span class="stat-num ${trendCls}">${c.trend_label}</span><span class="stat-lbl">${c.trend_pct >= 0 ? '+' : ''}${c.trend_pct}% trend</span></div>
        </div>
      </div>`;
  }).join('');

  const critCount = clusters.filter((c) => c.severity === 'critical').length;
  const subText = critCount > 0
    ? `<span style="color:var(--neg);font-weight:600;">${critCount} critical</span> · ${clusters.length} total · ${totalMentions} mentions`
    : `${clusters.length} themes · ${totalMentions} mentions`;

  $('#clusters-card').innerHTML = `
    <div class="card-head">
      <div>
        <div class="card-title">Top complaint clusters</div>
        <div class="card-sub">${subText}</div>
      </div>
      <div class="card-action">3-layer detection</div>
    </div>
    <div class="cluster-grid">${cards}</div>
  `;
}

/* ── Star distribution ────────────────────────────────────── */
function renderStarDist(d) {
  const a = d.aggregates;
  const total = a.total_reviews;
  const dist = a.rating_distribution;
  const rows = [5, 4, 3, 2, 1].map((r) => {
    const ct = dist[r] || 0;
    const pct = ct / total * 100;
    return `
      <div class="star-row r${r}">
        <span class="lbl">${r} <span class="sc">★</span></span>
        <div class="bar"><div style="width:${pct.toFixed(1)}%"></div></div>
        <span class="pct">${pct.toFixed(0)}%</span>
        <span class="ct">${ct}</span>
      </div>`;
  }).join('');

  const skew = (dist[5] || 0) / total > 0.5 ? 'top-heavy' : (dist[1] || 0) / total > 0.3 ? 'bottom-heavy' : 'balanced';

  const oneStarComplaints = d.one_star_complaints || [];
  const complaintLine = oneStarComplaints.length
    ? oneStarComplaints.map((c) => `${escape(c.label)} (${c.pct}%)`).join(', ')
    : `n = ${dist[1] || 0} one-star reviews`;

  $('#stardist-card').innerHTML = `
    <div class="card-head">
      <div>
        <div class="card-title">Star distribution</div>
        <div class="card-sub">Click a row to filter the explorer</div>
      </div>
    </div>
    <div class="avg-rating">
      <div class="num">${a.average_rating.toFixed(1)}</div>
      <div class="of">/ 5 average</div>
      <div class="meta">${total} ratings<br/>Skew · ${skew}</div>
    </div>
    <div class="star-dist">${rows}</div>
    <div style="padding: 12px 6px 0; margin-top: 10px; border-top: 1px solid var(--hair-2); font-size: 12px; color: var(--ink-2); line-height: 1.5;">
      <b>1-star reviewers complain about:</b> ${complaintLine}
    </div>
  `;
}

/* ── Certified-buyer split ────────────────────────────────── */
function renderCertifiedSplit(d) {
  const cb = d.cert_split || { verified: { rating: 0, count: 0, pct: 0, dist: [0, 0, 0] }, unverified: { rating: 0, count: 0, pct: 0, dist: [0, 0, 0] } };
  const vd = cb.verified.dist;
  const ud = cb.unverified.dist;
  const vTotal = vd[0] + vd[1] + vd[2] || 1;
  const uTotal = ud[0] + ud[1] + ud[2] || 1;

  const gap = Math.abs(cb.verified.rating - cb.unverified.rating);
  const showWarn = cb.unverified.count >= 5 && gap >= 0.5 && cb.unverified.rating > cb.verified.rating;
  const noUnverified = cb.unverified.count === 0;

  $('#cb-card').innerHTML = `
    <div class="card-head">
      <div>
        <div class="card-title">Certified vs uncertified buyers</div>
        <div class="card-sub">${noUnverified ? 'All reviews verified — no skew comparison possible' : 'Verified purchases tell a different story'}</div>
      </div>
    </div>
    <div class="cb-split">
      <div class="cb-card verified">
        <div class="cb-top">
          <span class="ic"><svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M2.5 6 5 8.5 9.5 3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
          Certified buyer
        </div>
        <div class="cb-num">${cb.verified.rating.toFixed(1)} <span class="stars">★</span></div>
        <div class="cb-meta">${cb.verified.count} reviews · ${cb.verified.pct}%</div>
        <div class="cb-bar">
          <div style="width:${(vd[0]/vTotal*100).toFixed(0)}%; background:var(--pos);"></div>
          <div style="width:${(vd[1]/vTotal*100).toFixed(0)}%; background:var(--neu);"></div>
          <div style="width:${(vd[2]/vTotal*100).toFixed(0)}%; background:var(--neg);"></div>
        </div>
      </div>
      <div class="cb-card">
        <div class="cb-top">
          <span class="ic"><svg width="11" height="11" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4" stroke="currentColor" stroke-width="1.4"/><path d="M6 4v3M6 8.2v.3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg></span>
          Uncertified
        </div>
        <div class="cb-num">${cb.unverified.count ? cb.unverified.rating.toFixed(1) : '—'} <span class="stars">★</span></div>
        <div class="cb-meta">${cb.unverified.count} reviews · ${cb.unverified.pct}%</div>
        <div class="cb-bar">
          <div style="width:${(ud[0]/uTotal*100).toFixed(0)}%; background:var(--pos);"></div>
          <div style="width:${(ud[1]/uTotal*100).toFixed(0)}%; background:var(--neu);"></div>
          <div style="width:${(ud[2]/uTotal*100).toFixed(0)}%; background:var(--neg);"></div>
        </div>
      </div>
    </div>
    ${showWarn ? `
      <div class="cb-warning">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style="flex-shrink:0; margin-top:1px;"><path d="M8 2 14 13H2L8 2Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M8 7v3M8 11.5v.3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
        <div><b>${gap.toFixed(1)}★ gap detected.</b> Uncertified reviews skew significantly more positive — possible incentivized reviews. Trust the certified-buyer score.</div>
      </div>` : noUnverified ? `
      <div class="cb-warning" style="background:var(--pos-soft);color:oklch(35% 0.13 152);border-color:oklch(85% 0.06 152);">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style="flex-shrink:0; margin-top:1px;"><path d="M2.5 8 6 11.5 13.5 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <div><b>100% verified.</b> Every review is from a confirmed Flipkart purchase — high baseline trust.</div>
      </div>` : ''}
  `;
}

/* ── Authenticity forensics ───────────────────────────────── */
function renderForensics(d) {
  const f = d.forensics || { score: 7.0, signals: [], burst_chart: [] };
  const signals = (f.signals || []).map((s) => `
    <div class="signal-row ${s.status}">
      <span class="ic">${s.status === 'ok'
        ? '<svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M2.5 6 5 8.5 9.5 3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
        : '<svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M6 2 11 10H1L6 2Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>'}
      </span>
      <div>
        <div class="name">${escape(s.name)}</div>
        <div class="sub">${escape(s.sub)}</div>
      </div>
      <span class="val">${escape(s.val)}</span>
    </div>`).join('');

  const burst = (f.burst_chart || []).map((h) => `<div class="bb${h >= 90 ? ' spike' : ''}" style="height:${h}%"></div>`).join('');
  const scoreColor = f.score >= 7 ? 'var(--pos-soft)' : f.score >= 5 ? 'var(--neu-soft)' : 'var(--neg-soft)';
  const scoreInk = f.score >= 7 ? 'oklch(40% 0.13 152)' : f.score >= 5 ? 'oklch(45% 0.15 60)' : 'oklch(45% 0.16 18)';

  $('#forensics-card').innerHTML = `
    <div class="card-head">
      <div>
        <div class="card-title">Authenticity forensics</div>
        <div class="card-sub">Evidence behind the trust score</div>
      </div>
      <span class="filter-pill on" style="cursor:default; background:${scoreColor}; color:${scoreInk}; border-color:${scoreColor};">${f.score.toFixed(1)} / 10</span>
    </div>
    <div class="signal-list">${signals}</div>
    ${burst ? `
      <div style="margin-top:12px; padding-top:10px; border-top:1px solid var(--hair-2);">
        <div style="font-size:10.5px; text-transform:uppercase; letter-spacing:0.06em; color:var(--ink-3); font-weight:600; margin-bottom:4px;">Review burst pattern · 12 weeks</div>
        <div class="burst-chart">${burst}</div>
      </div>` : ''}
  `;
}

/* ── Photo gallery ────────────────────────────────────────── */
function renderPhotos(d) {
  const card = $('#photo-card');
  const photos = d.photos || { total: 0, thumbs: [], clusters: {} };
  if (!photos.total) {
    card.style.display = 'none';
    return;
  }
  card.style.display = '';

  const thumbs = photos.thumbs.map((p) => {
    const flag = p.cluster === 'damaged' ? ' flag' : '';
    return `<div class="photo${flag}" style="background:#fff;background-image:url('${escape(p.url)}');background-size:cover;background-position:center;"><span class="photo-tag">${escape(p.cluster)}</span></div>`;
  }).join('');

  const more = photos.total > thumbs.length
    ? `<div class="photo more"><span>+ ${photos.total - photos.thumbs.length} more</span></div>` : '';

  const emojiMap = { unboxing: '📦', 'in-use': '🎧', compare: '📐', general: '📱', damaged: '⚠' };
  const clusterChips = Object.entries(photos.clusters).map(([k, c]) => {
    const isDanger = k === 'damaged';
    return `<div class="photo-cluster ${isDanger ? 'danger' : ''}">${emojiMap[k] || '📷'} ${escape(k.replace('-', ' '))} <span class="ct">${c}</span></div>`;
  }).join('');

  card.innerHTML = `
    <div class="card-head">
      <div>
        <div class="card-title">Buyer-uploaded photos</div>
        <div class="card-sub">${photos.total} photos clustered by what reviewers showed</div>
      </div>
      <span class="card-action">View all →</span>
    </div>
    <div class="photo-grid">${thumbs}${more}</div>
    <div class="photo-clusters">${clusterChips || ''}</div>
  `;
}

/* ── Variant breakdown ────────────────────────────────────── */
function renderVariants(d) {
  const card = $('#variant-card');
  const variants = d.variants || [];
  if (!variants.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = '';

  const attr = variants[0].attribute;
  const rows = variants.slice(0, 6).map((v) => {
    const total = v.pos + v.neu + v.neg || 1;
    const pP = (v.pos / total * 100).toFixed(0);
    const nP = (v.neu / total * 100).toFixed(0);
    const gP = (v.neg / total * 100).toFixed(0);
    const tag = v.tag || 'Standard';
    const cls = v.tag === 'Best rated' ? ' best' : v.tag === 'Lowest rated' ? ' worst' : '';
    return `
      <div class="variant-row${cls}">
        <div class="vname">${escape(v.value)} <span class="vtag">${escape(tag)}</span></div>
        <div class="vbar">
          <div style="width:${pP}%; background:var(--pos);"></div>
          <div style="width:${nP}%; background:var(--neu);"></div>
          <div style="width:${gP}%; background:var(--neg);"></div>
        </div>
        <div class="vstars">${v.avg_rating.toFixed(1)} ★</div>
        <div class="vct">${v.count}</div>
      </div>`;
  }).join('');

  const worst = variants[variants.length - 1];
  const worstNote = worst && worst.avg_rating <= 3.5
    ? `<div style="margin-top:12px; padding:10px 12px; background:var(--neg-soft); border:1px solid oklch(88% 0.06 18); border-radius:8px; font-size:12px; color:oklch(35% 0.16 18); line-height:1.5;">
         <b>${escape(worst.value)}</b> reviewers rate this variant ${worst.avg_rating.toFixed(1)}★ — significantly worse than the top variant. Consider another option.
       </div>`
    : '';

  card.innerHTML = `
    <div class="card-head">
      <div>
        <div class="card-title">Variant breakdown</div>
        <div class="card-sub">Sentiment by ${escape(attr.toLowerCase())} — pick the right one</div>
      </div>
      <span class="filter-pill on" style="cursor:pointer;">${escape(attr)}</span>
    </div>
    <div class="variant-grid">${rows}</div>
    ${worstNote}
  `;
}

/* ── Logistics vs product split ───────────────────────────── */
function renderLogisticsSplit(d) {
  const lp = d.logistics_split || null;
  if (!lp) return;
  const pa = lp.product;
  const la = lp.logistics;
  const pTotal = pa.pos + pa.neu + pa.neg || 1;
  const lTotal = la.pos + la.neu + la.neg || 1;

  const aspectRow = (name, val) => {
    const cls = val > 5 ? 'pos' : val < -5 ? 'neg' : 'neu';
    return `<div class="lp-asp"><span class="name">${escape(name)}</span><span class="v ${cls}">${fmtNet(val)}</span></div>`;
  };

  $('#lp-card').innerHTML = `
    <div class="card-head">
      <div>
        <div class="card-title">Product vs logistics sentiment</div>
        <div class="card-sub">Separating product quality from delivery & seller experience</div>
      </div>
    </div>
    <div class="lp-split">
      <div class="lp-card product">
        <div class="lp-head"><svg width="13" height="13" viewBox="0 0 16 16" fill="none"><rect x="3" y="5" width="10" height="8" rx="1.5" stroke="currentColor" stroke-width="1.5"/><path d="M6 5V3.5a2 2 0 0 1 4 0V5" stroke="currentColor" stroke-width="1.5"/></svg> The product itself</div>
        <div class="lp-net" style="color:var(--accent);">${fmtNet(pa.net)}</div>
        <div class="lp-bar">
          <div style="width:${(pa.pos/pTotal*100).toFixed(0)}%; background:var(--pos);"></div>
          <div style="width:${(pa.neu/pTotal*100).toFixed(0)}%; background:var(--neu);"></div>
          <div style="width:${(pa.neg/pTotal*100).toFixed(0)}%; background:var(--neg);"></div>
        </div>
        <div class="lp-asps">${(pa.aspects || []).map(([n, v]) => aspectRow(n, v)).join('')}</div>
      </div>
      <div class="lp-card logistics">
        <div class="lp-head"><svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M2 11h9V5H2zM11 8h3l1 2v1h-4" stroke="currentColor" stroke-width="1.5"/></svg> Delivery & seller</div>
        <div class="lp-net" style="color:oklch(50% 0.16 60);">${la.count ? fmtNet(la.net) : '—'}</div>
        <div class="lp-bar">
          <div style="width:${(la.pos/lTotal*100).toFixed(0)}%; background:var(--pos);"></div>
          <div style="width:${(la.neu/lTotal*100).toFixed(0)}%; background:var(--neu);"></div>
          <div style="width:${(la.neg/lTotal*100).toFixed(0)}%; background:var(--neg);"></div>
        </div>
        <div class="lp-asps">
          <div class="lp-asp"><span class="name">Logistics mentions</span><span class="v neu">${la.count}</span></div>
        </div>
      </div>
    </div>
    ${la.count > 0 ? `
      <div style="margin-top:12px; padding:10px 12px; background:var(--accent-soft); border-radius:8px; font-size:12px; color:var(--accent-ink); line-height:1.5;">
        <b>Reframe:</b> ${la.count} reviews (${la.pct}%) center on delivery/seller, not the product itself.
      </div>` : ''}
  `;
}

/* ── Buyer intelligence: What buyers actually use it for ──── */
function renderUseCases(d) {
  const card = $('#usecase-card');
  const items = d.use_cases || [];
  if (!items.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = '';

  const max = Math.max(...items.map((u) => u.mentions));
  const rows = items.slice(0, 6).map((u) => {
    const pct = (u.mentions / max * 100).toFixed(0);
    const tone = u.net >= 30 ? 'pos' : u.net <= -10 ? 'neg' : 'neu';
    const phrases = (u.sample_phrases || []).slice(0, 3)
      .map((p) => `"${escape(p)}"`).join(' · ');
    const iconSvg = ICON_PATHS[u.icon] || ICON_PATHS.spark;
    return `
      <div class="usecase-row">
        <div class="usecase-head">
          <span class="ic"><svg width="14" height="14" viewBox="0 0 16 16" fill="none">${iconSvg}</svg></span>
          <div class="usecase-meta">
            <div class="usecase-name">${escape(u.label)}</div>
            <div class="usecase-phrases">${phrases || '<i>—</i>'}</div>
          </div>
          <div class="usecase-stat">
            <div class="usecase-net ${tone}">${fmtNet(u.net)}</div>
            <div class="usecase-mentions">${u.mentions} mentions</div>
          </div>
        </div>
        <div class="usecase-bar">
          <div style="width:${pct}%; background:var(--${tone === 'pos' ? 'pos' : tone === 'neg' ? 'neg' : 'neu'});"></div>
        </div>
      </div>`;
  }).join('');

  card.innerHTML = `
    <div class="card-head">
      <div>
        <div class="card-title">What buyers actually use it for</div>
        <div class="card-sub">Auto-clustered from review context · sentiment per use-case</div>
      </div>
      <span class="card-action">${items.length} clusters</span>
    </div>
    <div class="usecase-list">${rows}</div>
  `;
}

/* ── Buyer intelligence: Who's reviewing this ─────────────── */
function renderReviewerProfile(d) {
  const card = $('#reviewer-profile-card');
  const r = d.reviewer_profile;
  if (!r) {
    card.style.display = 'none';
    return;
  }
  card.style.display = '';

  // City tier 3-band split
  const t = r.by_tier || {};
  const tierBar = (t.placed || 0) > 0 ? `
    <div class="tier-bar">
      <div class="tier-seg tier1" style="width:${t.tier1_pct}%;">Tier 1 · ${t.tier1_pct}%</div>
      <div class="tier-seg tier2" style="width:${t.tier2_pct}%;">Tier 2 · ${t.tier2_pct}%</div>
      <div class="tier-seg tier3" style="width:${t.tier3_pct}%;">Tier 3 · ${t.tier3_pct}%</div>
    </div>` : '<div style="font-size:12px;color:var(--ink-4);">No location data</div>';

  const cities = (r.top_cities || []).slice(0, 5)
    .map((c) => `<span class="city-pill">${escape(c.name)} <span class="ct">${c.count}</span></span>`).join('');

  const metrics = (r.metrics || []).slice(0, 6).map((m) => `
    <div class="metric-tile">
      <div class="metric-val">${escape(m.value)}</div>
      <div class="metric-label">${escape(m.label)}</div>
      <div class="metric-sub">${escape(m.sub)}</div>
    </div>`).join('');

  card.innerHTML = `
    <div class="card-head">
      <div>
        <div class="card-title">Who's reviewing this</div>
        <div class="card-sub">Geographic + buyer profile distribution</div>
      </div>
      <span class="card-action">${r.total_reviews} reviewers</span>
    </div>
    <div class="rp-section-label">By city tier</div>
    ${tierBar}
    <div class="city-pills">${cities}</div>
    <div class="rp-section-label" style="margin-top:14px;">Reviewer profile</div>
    <div class="metric-grid">${metrics}</div>
  `;
}

/* ── AI Smart summary ─────────────────────────────────────── */
function renderAISummary(d) {
  const summary = d.summary || { pros: [], cons: [] };
  const pros = (summary.pros || []).slice(0, 3).map((p, i) => `
    <li><span class="num">${i + 1}</span><div><b>${escape(p.phrase)}</b> — recurring praise across reviews. <span style="color:var(--ink-3);">(${p.count} mentions)</span></div></li>`).join('');
  const cons = (summary.cons || []).slice(0, 3).map((p, i) => `
    <li><span class="num">${i + 1}</span><div><b>${escape(p.phrase)}</b> — recurring complaint. <span style="color:var(--ink-3);">(${p.count} mentions)</span></div></li>`).join('');

  const wsb = d.who_should_buy || { paragraph: '', for_tags: [], against_tags: [] };
  const tags = wsb.for_tags.map((t) => `<span class="who-tag">✓ ${escape(t)}</span>`).join('') +
               wsb.against_tags.map((t) => `<span class="who-tag gray">✗ ${escape(t)}</span>`).join('');

  $('#ai-card').innerHTML = `
    <div class="ai-head">
      <div class="ai-badge"><svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 2v4M8 10v4M2 8h4M10 8h4M3.5 3.5l2.8 2.8M9.7 9.7l2.8 2.8M3.5 12.5l2.8-2.8M9.7 6.3l2.8-2.8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></div>
      <div class="ai-title">AI-generated summary</div>
      <div class="ai-pill"><span class="pulse-dot"></span>Grounded · ${d.meta.review_count} sources</div>
    </div>
    <div class="ai-grid">
      <div class="ai-block pros">
        <h4>Top pros</h4>
        <ul class="ai-list">${pros || '<li><div style="color:var(--ink-3);">No clear positive themes detected.</div></li>'}</ul>
      </div>
      <div class="ai-block cons">
        <h4>Top cons</h4>
        <ul class="ai-list">${cons || '<li><div style="color:var(--ink-3);">No clear negative themes detected.</div></li>'}</ul>
      </div>
    </div>
    <div class="who">
      <h4>Who should buy this</h4>
      ${escape(wsb.paragraph || 'Based on the analysis, consider whether the top concerns affect your use case.')}
      <div class="who-tags">${tags}</div>
    </div>
  `;
}

/* ── Review explorer ──────────────────────────────────────── */
function renderExplorer(d) {
  const aspects = d.aspects || {};
  const aspectKeys = Object.keys(aspects).filter((k) => aspects[k].mentions > 0);

  const filterBar = `
    <span class="filter-label">Sentiment</span>
    <span class="filter-pill ${FILTER.sentiment === 'all' ? 'on' : ''}" data-f-sent="all">All <span class="count">${d.aggregates.total_reviews}</span></span>
    <span class="filter-pill ${FILTER.sentiment === 'positive' ? 'on' : ''}" data-f-sent="positive"><span style="width:6px;height:6px;border-radius:50%;background:var(--pos);display:inline-block;"></span>Positive <span class="count">${d.aggregates.sentiment_distribution.positive || 0}</span></span>
    <span class="filter-pill ${FILTER.sentiment === 'neutral' ? 'on' : ''}" data-f-sent="neutral"><span style="width:6px;height:6px;border-radius:50%;background:var(--neu);display:inline-block;"></span>Neutral <span class="count">${d.aggregates.sentiment_distribution.neutral || 0}</span></span>
    <span class="filter-pill ${FILTER.sentiment === 'negative' ? 'on' : ''}" data-f-sent="negative"><span style="width:6px;height:6px;border-radius:50%;background:var(--neg);display:inline-block;"></span>Negative <span class="count">${d.aggregates.sentiment_distribution.negative || 0}</span></span>
    <span class="filter-sep"></span>
    <span class="filter-label">Feature</span>
    ${aspectKeys.slice(0, 5).map((k) => `<span class="filter-pill ${FILTER.feature === k ? 'on' : ''}" data-f-feat="${k}">${escape(aspectLabel(k))}</span>`).join('')}
    <span class="filter-sep"></span>
    <span class="filter-label">Rating</span>
    <span class="filter-pill ${FILTER.rating === 'low' ? 'on' : ''}" data-f-rating="low">★ 1–2</span>
    <span class="filter-pill ${FILTER.rating === 'mid' ? 'on' : ''}" data-f-rating="mid">★ 3</span>
    <span class="filter-pill ${FILTER.rating === 'high' ? 'on' : ''}" data-f-rating="high">★ 4–5</span>
    <span class="filter-clear" id="filter-clear">Clear all</span>
  `;

  const filtered = filterReviews(d).slice(0, 20);
  const reviews = filtered.map(reviewRow).join('');

  $('#explorer').innerHTML = `
    <div class="explorer-head">
      <span class="explorer-title">Reviews</span>
      <span class="explorer-sub" id="explorer-sub">${filtered.length} of ${d.aggregates.total_reviews} shown</span>
      <div class="explorer-search">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><circle cx="7" cy="7" r="4.5" stroke="currentColor" stroke-width="1.5"/><path d="m10.5 10.5 3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
        <input id="explorer-search-input" placeholder="Search within reviews…" />
        <span class="mono" style="font-size:10.5px; color:var(--ink-4); border:1px solid var(--hair); padding:1px 5px; border-radius:4px;">⌘K</span>
      </div>
    </div>
    <div class="filter-bar">${filterBar}</div>
    <div class="review-list">${reviews || '<div style="padding:40px;text-align:center;color:var(--ink-3);font-size:13px;">No reviews match the current filters.</div>'}</div>
    <div class="explorer-foot">
      <span>Showing <b style="color:var(--ink);">1–${Math.min(20, filtered.length)}</b> of ${d.aggregates.total_reviews}</span>
    </div>
  `;

  $$('[data-f-sent]').forEach((el) => el.addEventListener('click', () => {
    FILTER.sentiment = el.dataset.fSent;
    renderExplorer(DATA);
  }));
  $$('[data-f-feat]').forEach((el) => el.addEventListener('click', () => {
    FILTER.feature = FILTER.feature === el.dataset.fFeat ? null : el.dataset.fFeat;
    renderExplorer(DATA);
  }));
  $$('[data-f-rating]').forEach((el) => el.addEventListener('click', () => {
    FILTER.rating = FILTER.rating === el.dataset.fRating ? null : el.dataset.fRating;
    renderExplorer(DATA);
  }));
  $('#filter-clear').addEventListener('click', () => {
    FILTER = { sentiment: 'all', feature: null, rating: null };
    renderExplorer(DATA);
  });
  $('#explorer-search-input').addEventListener('input', debounce(() => renderExplorer(DATA), 200));
}

function filterReviews(d) {
  const s = $('#explorer-search-input')?.value?.trim().toLowerCase() || '';
  let ids = Object.keys(d.reviews);
  if (FILTER.sentiment && FILTER.sentiment !== 'all') {
    ids = intersect(ids, d.filters.by_sentiment[FILTER.sentiment] || []);
  }
  if (FILTER.feature) {
    ids = intersect(ids, d.filters.by_aspect[FILTER.feature] || []);
  }
  if (FILTER.rating === 'low') {
    const lo = (d.filters.by_rating['1'] || []).concat(d.filters.by_rating['2'] || []);
    ids = intersect(ids, lo);
  } else if (FILTER.rating === 'mid') {
    ids = intersect(ids, d.filters.by_rating['3'] || []);
  } else if (FILTER.rating === 'high') {
    const hi = (d.filters.by_rating['4'] || []).concat(d.filters.by_rating['5'] || []);
    ids = intersect(ids, hi);
  }
  let out = ids.map((id) => d.reviews[id]);
  if (s) out = out.filter((r) => (r.comment.text + ' ' + r.title.text).toLowerCase().includes(s));
  out.sort((a, b) => b.engagement.helpful_count - a.engagement.helpful_count);
  return out;
}

function reviewRow(r) {
  const stars = Array.from({ length: 5 }, (_, i) =>
    `<svg ${i >= r.rating ? 'class="empty"' : ''} viewBox="0 0 16 16" fill="currentColor"><path d="M8 1.5l1.9 4 4.4.6-3.2 3.1.8 4.4L8 11.5 4.1 13.6l.8-4.4-3.2-3.1 4.4-.6L8 1.5Z"/></svg>`
  ).join('');
  const dateStr = r.date.raw || '';
  const sent = r.analysis.sentiment_label;
  const aspectTags = (r.aspects_present || []).slice(0, 3).map((a) => `<span class="rtag">${escape(a)}</span>`).join('');
  return `
    <div class="review">
      <div class="review-meta">
        <div class="stars-mini">${stars}</div>
        <span class="author">${escape(r.author.name)}</span>
        <span class="date">${escape(dateStr)} · ${r.author.verified ? 'Verified' : 'Unverified'}</span>
      </div>
      <div>
        <div class="review-body">${escape(r.comment.text)}</div>
        <div class="review-tags">${aspectTags}</div>
      </div>
      <div class="review-side">
        <span class="sent-badge ${sent === 'positive' ? 'pos' : sent === 'negative' ? 'neg' : 'neu'}">${sent === 'positive' ? 'Positive' : sent === 'negative' ? 'Negative' : 'Mixed'}</span>
        <span class="helpful">
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none"><path d="M5 7v6H2V7h3Zm0 0 3-5c1 0 2 .5 2 2v2h3.5c1 0 1.5 1 1.2 2l-1.2 4c-.2.7-.7 1-1.5 1H5" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>
          ${r.engagement.helpful_count} helpful
        </span>
      </div>
    </div>`;
}

/* ── Helpers ──────────────────────────────────────────────── */
function intersect(a, b) {
  const set = new Set(b);
  return a.filter((x) => set.has(x));
}
function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
