# ReviewPulse

**Flipkart product review intelligence — scrape every review, mine what matters, render a premium dashboard.**

ReviewPulse turns a Flipkart product URL into a structured analytical report. Where Flipkart shows you a 4.4-star average and the top-five most-helpful reviews, ReviewPulse pulls every available review, extracts the product's full spec sheet, runs aspect-based sentiment analysis across category-specific feature taxonomies, clusters complaints into recurring themes, surfaces hidden upsides and flaws the seller didn't advertise, and presents it all on a Linear-inspired dashboard.

> **3,505 reviews — scraped, enriched, clustered, and rendered in ~25 seconds.**

---

## What it does

You paste a Flipkart URL. The backend simultaneously scrapes the product page (extracting title, brand, breadcrumb, 26+ specs, pricing, image gallery) and the full review corpus using a 20-thread parallel scraper that walks Flipkart's deep pagination across multiple sort/filter windows and deduplicates by review UUID. Every review is enriched with VADER sentiment, sentence-level aspect mentions, parsed dates (handling `Feb, 2024` and `10 months ago` alike), city-tier classification, and image/attribute extraction. The aggregated data drives a 4-section dashboard:

- **Key Insights** — sentiment overview, feature-wise sentiment, verdict, complaint clusters
- **Product details** — claim-vs-reality alignment, reviewer surprises, full specs
- **Deeper analysis** — star distribution, certified-buyer split, authenticity forensics, photos, variants, product-vs-logistics split
- **Buyer intelligence** — use-case clustering, geographic + reviewer profile distribution

Plus a **Smart summary** with auto-mined pros/cons and a filterable **Review explorer**.

---

## Quickstart

```bash
git clone https://github.com/StartrekI/ReviewPulse.git
cd ReviewPulse
pip install -r requirements.txt
python web_app.py
```

Open **http://127.0.0.1:5050**, paste any Flipkart product URL (the `/p/itm…` form), click **Analyze product**, and wait ~25 seconds.

---

## Highlight features

### Scraper

- **Parallel deep pagination** — `ThreadPoolExecutor(max_workers=20)` splits the page range into 20-page batches and fetches them concurrently. Lifts the per-filter cap from 30 pages → 350 pages, achieving ~98% coverage of the actual review corpus.
- **TLS impersonation** — `curl_cffi` with Chrome fingerprinting bypasses Flipkart's bot detection.
- **Brace-balanced JSON parsing** — extracts `window.__INITIAL_STATE__` (a 1-MB embedded JSON blob) by walking the brace structure, since the standard non-greedy regex truncates early.
- **Multi-sort dedup fallback** — optional mode that walks `MOST_HELPFUL`, `MOST_RECENT`, `POSITIVE_FIRST`, `NEGATIVE_FIRST` × `certifiedBuyer ∈ {true, false}` windows and merges by review UUID for absolute coverage.

### Analysis

- **Aspect-Based Sentiment Analysis** with **12 product-category taxonomies** (earbuds, smartphone, laptop, smartwatch, TV, kitchen appliance, mattress, footwear, apparel, bag, skincare, generic fallback). Auto-detects category from the breadcrumb path.
- **Three-layer complaint clustering**:
  1. **Pattern archetypes** — handcrafted regex for 12 common complaint types (defective on arrival, battery degradation, open-box damage, fake product, misleading specs, noise/distortion, connectivity drops, fit/comfort, warranty issues, size/color mismatch, etc.). Each archetype produces a labeled cluster with severity tier, MoM trend, exemplar review.
  2. **Aspect-anchored clusters** — when an aspect has ≥3 negative mentions and ≥20% negative share, surfaces those reviews as a per-aspect cluster.
  3. **KMeans residual** — TF-IDF + KMeans on remaining unclassified negative reviews to catch anything the patterns missed.
- **Spec ↔ Review alignment** — pairs each scraped spec key (`Noise Cancellation: Yes`, `Battery: 7hr`, etc.) with the corresponding aspect's review sentiment to produce a "Lives up to spec / Mixed / Underperforms" verdict per claim.
- **Reviewer surprises** — gap analysis. Aspects with ≥5 mentions and meaningful sentiment that map to **no** spec key. Splits into "Hidden upsides" (good things the seller didn't advertise) and "Hidden flaws" (bad things they hid).
- **Use-case clustering** — per-category use-case taxonomies match review text to inferred buyer intents (Music listening, Office calls, Workout & gym, Travel, Gift, etc.) with sentiment per use-case.
- **City-tier classification** — Indian cities mapped to Tier 1 / 2 / 3 sets for geographic distribution.
- **Authenticity forensics** — verified-buyer ratio, review-burst spike detection, duplicate-phrase detection, review-depth scoring, 12-week burst histogram, composite trust score (0–10).
- **Reviewer profile metrics** — verified %, median review tenure (proxy for account age), detailed-review %, photo-attached %, helpful-vote rate, multiline structure %.
- **Verdict computation** — Worth buying / Mixed / Skip + confidence% + supporting bullet points based on rating distribution and aspect strengths/weaknesses.
- **Smart summary** — heuristic pros/cons mining (contrastive-conjunction splitting on "but", "however") + who-should-buy paragraph + persona tags.
- **Time-series** — monthly buckets across the entire scraped corpus (handles both absolute "Feb, 2024" and relative "10 months ago" date formats), with avg sentiment / avg rating / volume per month.
- **Variant breakdown** — when reviews carry `productAttributeList` data, groups by primary attribute (color/size/etc.) and shows per-variant rating + sentiment split.

### Dashboard

- Linear-inspired warm off-white theme with single indigo accent (oklch palette).
- Geist + Geist Mono typography with `font-variant-numeric: tabular-nums` on all numeric data.
- 12-column bento grid with adaptive column redistribution (cards expand to fill rows when neighbors are hidden).
- Interactive sentiment trend with **12M / 6M / 3M** range toggles + hover tooltips per month.
- Filterable review explorer (sentiment × feature × rating × keyword search) with O(1) inverted-index lookups.
- Empty cards auto-hide instead of showing placeholder content.

---

## Pipeline

```
URL ──▶ scrape_product_page()
        ├─ title, brand, breadcrumb
        ├─ price, MRP, discount
        ├─ 26+ spec key-value pairs
        ├─ highlights, description
        └─ image gallery URLs
                                  │
        scrape_all_reviews()      │  parallel · 20 workers · ~17s for 3500 reviews
        ├─ author, rating, title  │
        ├─ comment text, date     │
        ├─ helpful, verified      │
        ├─ city, state            │
        └─ attrs, image URLs ─────┤
                                  ▼
                       enrich_review() per-review:
                       ├─ VADER sentiment compound
                       ├─ sentence-level aspect mentions
                       ├─ flexible date parser (absolute + relative)
                       ├─ city-tier classification
                       ├─ length bucket, emoji flag, multiline flag
                       ├─ feature-breakdown detection
                       ├─ logistics-mention detection
                       └─ rating-sentiment mismatch flag
                                  │
                                  ▼
        ┌─────────────── analysis layer ────────────────────────┐
        │  aggregate_aspects   ─▶ per-aspect ABSA rollup         │
        │  cluster_complaints  ─▶ 3-layer cluster engine         │
        │  align_specs_with_   ─▶ spec-claim vs review reality   │
        │  find_reviewer_surp  ─▶ aspects buyers care about that │
        │                         the listing didn't mention     │
        │  compute_use_cases   ─▶ buyer-intent clustering        │
        │  compute_reviewer_p  ─▶ city tier + profile metrics    │
        │  compute_forensics   ─▶ authenticity signals + burst   │
        │  compute_logistics_  ─▶ product vs delivery split      │
        │  compute_certified_  ─▶ verified vs unverified split   │
        │  compute_verdict     ─▶ worth-buying decision + conf%  │
        │  build_timeseries    ─▶ monthly volume + sentiment     │
        │  extract_pros_cons   ─▶ contrastive-conjunction mining │
        └────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                     JSON response (schema 4.0)
                                  │
                                  ▼
                     renderAll() in static/app.js
                     ├─ clearAllCards (wipe demo HTML)
                     ├─ safeRun each render fn (try/catch)
                     ├─ adjustGridLayout (rebalance cols)
                     └─ scroll to top
```

---

## Dashboard sections

### Hero
Empty-state landing — clean URL bar in the center, scope chips, an Analyze button. Loader appears with elapsed-seconds counter while the pipeline runs.

### Product card
Real product image (Flipkart hero shot), brand line, title, star average, total rating count, price line (₹final / ₹MRP / N% off), URL pill, and a 4-cell stat strip:
- **Sentiment** — net sentiment score (positive% − negative%)
- **Reviews analyzed** — actual scraped count
- **Pos · Neg** — sentiment percentage split
- **Trust score** — composite authenticity rating

### Key insights

| Card | Width | Content |
|---|---|---|
| Sentiment overview | 4 cols | Donut chart with sentiment split + insight quote with top/bottom aspects |
| Feature-wise sentiment | 5 cols | Top 6 aspects with net score + stacked pos/neu/neg bar |
| Verdict | 3 cols | Worth buying / Mixed / Skip + confidence% + 4 supporting bullets |
| Top complaint clusters | 12 cols | 3-up grid of cluster cards with severity tier, mention count, avg rating, MoM trend |

### Product details

| Card | Width | Content |
|---|---|---|
| Claim vs reality | 7 cols | 12 spec claims paired with review-mined aspect sentiment + Match / Mixed / Miss verdict |
| Reviewer surprises | 5 cols | Aspects with strong sentiment that don't map to any spec — split into Hidden upsides ✓ and Hidden flaws ✗ |
| Full specifications | 12 cols | All 26+ scraped spec key-value pairs in a 2-column grid |

### Deeper analysis

| Card | Width | Content |
|---|---|---|
| Star distribution | 4 cols | 5★/4★/3★/2★/1★ percentage bars + skew label + 1-star complaint themes |
| Certified vs uncertified | 4 cols | Verified-buyer rating vs unverified rating, with gap-warning if uncertified skews positive |
| Authenticity forensics | 4 cols | Trust score + 4 signal rows + 12-week burst chart |
| Buyer photos · Variants · Logistics | 5–7 cols (adaptive) | Photo gallery if Flipkart returned media · variant breakdown if reviews have attribute splits · product-vs-logistics sentiment split |

### Buyer intelligence

| Card | Width | Content |
|---|---|---|
| What buyers actually use it for | 6 cols | Up to 6 use-case clusters with sentiment + sample phrases + bar |
| Who's reviewing this | 6 cols | Tier-1/2/3 city distribution + top-5 city pills + 4-tile reviewer-profile metrics |

### Smart summary
Single full-width card with auto-mined pros (left) and cons (right) from contrastive-conjunction splits, plus a "Who should buy this" paragraph + persona tags.

### Review explorer
Filter pills (sentiment × feature × rating × keyword search) + helpful-sorted review cards with stars, sentiment chip, aspect tags, and `mismatch` / `logistics` indicators. Live filtering via O(1) set-intersection on pre-computed inverted indexes.

---

## Tech stack

**Backend**
- Python 3.10+
- Flask (web server + JSON API)
- curl_cffi (Chrome-impersonating HTTP for Flipkart)
- BeautifulSoup4 (HTML parsing fallback)
- pandas (DataFrame ops)
- scikit-learn (TF-IDF + KMeans for residual clustering)
- vaderSentiment (lexicon-based sentiment scoring)
- dateparser (relative date fallback parser)
- concurrent.futures (parallel scraping)

**Frontend**
- Vanilla HTML / CSS / JavaScript (no React, no build step)
- Geist + Geist Mono via Google Fonts
- Hand-coded SVG charts (no Chart.js / D3)
- oklch color space for the design tokens

**Design**
- Linear-inspired warm off-white base, indigo accent
- 12-column bento grid with `align-items: stretch`
- 8 px corner radius, 1 px borders, no drop shadows
- 4 px spacing rhythm

---

## Project structure

```
ReviewPulse/
├── web_app.py              Flask server + /analyze endpoint
├── scrape_product.py       Product page scraper (specs, breadcrumb, etc.)
├── scrape_all_reviews.py   Parallel review scraper (20-worker thread pool)
├── analysis_v2.py          ABSA, clustering, alignment, forensics, verdict
├── category_taxonomies.py  12 product-category taxonomies + use-cases + city tiers
├── export_json.py          Per-review enrichment + aggregates + filter indexes
├── requirements.txt        Python deps
├── templates/
│   └── index.html          Single-page dashboard layout
├── static/
│   ├── style.css           Linear-inspired design system
│   ├── app.js              Render orchestration + interactivity
│   └── shared.js           Sidebar injector
├── asset/                  Screenshots
├── DESIGN_PROPOSAL.md      Original 5-part research document
├── FEATURES.txt            Plain-text feature documentation
└── app.py                  Original Streamlit prototype (kept for reference)
```

---

## Adding a new product category

The category taxonomy lives in `category_taxonomies.py`. To support a new category (say, books):

1. Add a key under `CATEGORIES`:
   ```python
   "books": {
       "label": "Books",
       "url_keywords": ["book", "novel", "paperback", "hardcover"],
       "title_keywords": ["book", "novel", "edition"],
       "aspects": {
           "writing":   {"label": "Writing quality", "icon": "diamond", "keywords": ["writ", "prose", "style"]},
           "story":     {"label": "Story / plot",    "icon": "spark",   "keywords": ["story", "plot", "character", "twist"]},
           "print":     {"label": "Print quality",   "icon": "shield",  "keywords": ["print", "paper", "binding", "cover"]},
           "value":     {"label": "Value",           "icon": "rupee",   "keywords": ["price", "cost", "worth"]},
       },
   },
   ```

2. Add the matching `USE_CASES` entry for buyer-intent clustering.

3. Optionally add spec-key → aspect hints in `analysis_v2.py` `SPEC_TO_ASPECT_HINTS` so the spec-alignment pairs new spec fields with the new aspects.

The pipeline picks it up automatically — no other changes needed.

---

## Limitations & Flipkart-specific notes

- **Review cap.** Flipkart caps each filter window at ~30 pages × 10 reviews. The parallel scraper lifts this to ~350 pages by going deep on the `MOST_HELPFUL` sort, but ~1-2% of reviews at the corpus boundary remain unreachable. Multi-pass mode (off by default) walks alternative sorts to backfill.
- **Image / variant data is product-dependent.** Flipkart sometimes returns review-attached images and `productAttributeList` arrays per review, sometimes not. When absent, the Photos and Variants cards auto-hide.
- **Total reviews vs total ratings.** Flipkart's UI shows a "ratings" count (54,411 for OnePlus Buds 3) which includes anonymous star-only ratings. The actually scrapable count is the "reviews" number (3,505) — only those have text content.
- **Date parsing.** Flipkart returns dates as `Feb, 2024` for old reviews and `10 months ago` for recent ones. The parser handles both.
- **Sentiment engine.** VADER is rule-based; works well for short product reviews but can be fooled by sarcasm or polite-but-negative language. The `rating_sentiment_mismatch` flag surfaces these cases.

---

## Why this exists

Flipkart's product page surfaces an average rating, a sentiment-sorted preview of a few reviews, and that's about it. For products with thousands of reviews (every popular SKU), there's no efficient way to:

- See which advertised features actually live up to the claim
- Spot recurring complaint patterns before buying
- Distinguish product issues from delivery/seller issues
- Identify hidden flaws the listing doesn't disclose
- Understand who's actually buying it (city tier, use case, reviewer credibility)

ReviewPulse computes all of this in ~25 seconds and renders it on a single dashboard.

---

## Roadmap

- [ ] Persistent analysis cache (so re-analyzing a recently-scraped product is instant)
- [ ] CSV / PDF export of the full report
- [ ] Multi-product comparison view
- [ ] Q&A scraping (the buyer-question section on Flipkart product pages)
- [ ] Saved analyses / collections workspace
- [ ] Real LLM integration for the Smart Summary (currently heuristic)
- [ ] Support for Amazon and other Indian e-commerce sites

---

## Acknowledgements

The dashboard design language draws on Linear, Vercel's Geist design system, and Stripe's analytical UI conventions. The clustering and aspect-extraction approaches are informed by published work on aspect-based sentiment analysis and Yotpo / Bazaarvoice's commercial review-intelligence products.

Built with Flask, curl_cffi, vaderSentiment, scikit-learn, and a lot of attention to detail.
