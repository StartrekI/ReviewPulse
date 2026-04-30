"""
Flipkart Review Scraper — robust JSON-based extraction.

Flipkart serves the page state as `window.__INITIAL_STATE__` JSON. We parse
that instead of scraping CSS classes (which Flipkart obfuscates and rotates).

Accepts any Flipkart product URL (/p/) or reviews URL (/product-reviews/).
"""

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import pandas as pd
from curl_cffi import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()

INITIAL_STATE_RE = re.compile(
    r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});\s*</script>", re.DOTALL
)


def fetch(url, retries=3, delay=1.5):
    for attempt in range(retries):
        try:
            r = requests.get(url, impersonate="chrome", timeout=20)
            if r.status_code == 200:
                return r.text
            print(f"  [warn] HTTP {r.status_code} attempt {attempt + 1}")
        except Exception as e:
            print(f"  [warn] {type(e).__name__}: {e}")
        time.sleep(delay * (attempt + 1))
    return None


def to_reviews_url(url):
    """Convert /p/ product URL to /product-reviews/ URL. Pass-through if already reviews."""
    parsed = urlparse(url)
    if "/product-reviews/" in parsed.path:
        return url
    if "/p/" not in parsed.path:
        raise ValueError("Not a Flipkart product URL.")

    new_path = parsed.path.replace("/p/", "/product-reviews/", 1)
    params = parse_qs(parsed.query)
    keep = {k: v[0] for k, v in params.items()
            if k in ("pid", "lid", "marketplace")}
    keep.setdefault("marketplace", "FLIPKART")
    return urlunparse(parsed._replace(path=new_path, query=urlencode(keep)))


def extract_state(html):
    m = INITIAL_STATE_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def extract_reviews(state):
    """Pull review objects from slots whose elementId ends in '-REVIEWS'.

    Returns (reviews, real_review_count). The real count comes from the
    rating-summary widget where Flipkart exposes the truthful number
    (e.g., 3505 for OnePlus Buds 3) — not the per-page totalCount field
    which only reflects the current pagination context.
    """
    reviews = []
    real_count = None
    try:
        slots = state["multiWidgetState"]["widgetsData"]["slots"]
    except (KeyError, TypeError):
        return reviews, real_count

    # Truthful count from rating widget (slot may vary, scan all)
    for slot in slots:
        try:
            rating = slot["slotData"]["widget"]["data"].get("rating", {})
            rc = rating.get("value", {}).get("reviewCount") if isinstance(rating, dict) else None
            if rc and rc > 0:
                real_count = rc
                break
        except (KeyError, TypeError, AttributeError):
            continue

    for slot in slots:
        sd = slot.get("slotData", {})
        if not sd.get("elementId", "").endswith("-REVIEWS"):
            continue
        rcs = sd.get("widget", {}).get("data", {}).get("renderableComponents", [])
        for rc in rcs:
            v = rc.get("value", {}) or {}
            if v.get("type") != "ProductReviewValue":
                continue
            # If we didn't find a rating-widget total, fall back to the
            # per-review totalCount (less reliable; usually a per-listing subset).
            if real_count is None and v.get("totalCount"):
                real_count = v.get("totalCount")
            loc = v.get("location") or {}
            attrs = v.get("productAttributeList") or []
            attrs_dict = {a.get("name", "").lower(): a.get("value", "") for a in attrs if a.get("name")}
            images = v.get("images") or v.get("media") or []
            image_urls = []
            for img in images:
                if isinstance(img, dict):
                    url = img.get("url") or img.get("src") or img.get("imageUrl")
                    if url: image_urls.append(url)
                elif isinstance(img, str):
                    image_urls.append(img)
            reviews.append({
                "ReviewId":       v.get("id"),
                "Customer Name":  v.get("author"),
                "Rating":         v.get("rating"),
                "Review Title":   v.get("title"),
                "Comment":        v.get("text") or "",
                "Date":           v.get("created"),
                "Helpful":        v.get("helpfulCount"),
                "Verified":       v.get("certifiedBuyer"),
                "City":           loc.get("city"),
                "State":          loc.get("state"),
                "Attrs":          json.dumps(attrs_dict, ensure_ascii=False) if attrs_dict else "",
                "Images":         json.dumps(image_urls, ensure_ascii=False) if image_urls else "",
            })
    return reviews, real_count


SORT_PASSES = [
    # (sortOrder, certifiedBuyer) — Flipkart caps each pass at ~30 pages.
    # We run them all and dedupe by review UUID for max coverage.
    ("MOST_HELPFUL",   "false"),
    ("MOST_RECENT",    "false"),
    ("POSITIVE_FIRST", "false"),
    ("NEGATIVE_FIRST", "false"),
    ("MOST_HELPFUL",   "true"),
    ("MOST_RECENT",    "true"),
]


def _scrape_page_range(pass_url, start_page, end_page, polite_delay):
    """Worker — sequentially fetch pages [start_page, end_page] within one batch.
    Returns list of review dicts. Stops early after 2 consecutive empties."""
    rows = []
    empty_streak = 0
    for i in range(start_page, end_page + 1):
        if i > start_page and polite_delay > 0:
            time.sleep(polite_delay)
        html = fetch(f"{pass_url}&page={i}", retries=2, delay=0.8)
        if html is None:
            empty_streak += 1
            if empty_streak >= 3: break
            continue
        state = extract_state(html)
        if state is None:
            empty_streak += 1
            if empty_streak >= 3: break
            continue
        page_rows, _ = extract_reviews(state)
        if not page_rows:
            empty_streak += 1
            if empty_streak >= 2: break
            continue
        empty_streak = 0
        rows.extend(page_rows)
    return rows


def _scrape_single_pass(reviews_url, sort_order, cert_buyer, max_pages,
                        polite_delay, max_workers=20, batch_size=20):
    """Scrape one (sortOrder × certifiedBuyer) window using parallel batches.

    1. Fetch page 1 to get the truthful reviewCount.
    2. Compute total_pages = ceil(reviewCount / 10), capped at 350.
    3. Split [2..total_pages] into batches of `batch_size` pages.
    4. Submit each batch to a thread-pool worker.
    5. Merge as workers complete.
    """
    sep = "&" if "?" in reviews_url else "?"
    pass_url = f"{reviews_url}{sep}aid=overall&sortOrder={sort_order}&certifiedBuyer={cert_buyer}"
    print(f"[pass] sort={sort_order:15s} cert={cert_buyer}")

    html = fetch(f"{pass_url}&page=1", retries=3, delay=1.0)
    if html is None:
        return [], 0
    state = extract_state(html)
    if state is None:
        return [], 0

    rows, real_total = extract_reviews(state)
    per_page = max(len(rows), 1)
    target_pages = min((real_total + per_page - 1) // per_page if real_total else 50, 350)
    if max_pages:
        target_pages = min(target_pages, max_pages)

    if target_pages <= 1:
        print(f"  → {len(rows)} reviews (single page)")
        return rows, real_total

    # Build batches over pages 2..target_pages
    batches: list[tuple[int, int]] = []
    p = 2
    while p <= target_pages:
        batches.append((p, min(p + batch_size - 1, target_pages)))
        p += batch_size

    print(f"  parallel: {target_pages} pages in {len(batches)} batches × {batch_size} pp · {max_workers} workers")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_scrape_page_range, pass_url, s, e, polite_delay): (s, e)
            for s, e in batches
        }
        completed = 0
        for fut in as_completed(futures):
            s, e = futures[fut]
            try:
                batch_rows = fut.result()
            except Exception as exc:
                print(f"  batch {s:3d}-{e:3d} failed: {type(exc).__name__}: {exc}")
                continue
            completed += 1
            rows.extend(batch_rows)
            if completed % 5 == 0 or completed == len(batches):
                elapsed = time.time() - t0
                print(f"  [{completed:2d}/{len(batches):2d} batches] running total: {len(rows)} reviews · {elapsed:.1f}s")

    elapsed = time.time() - t0
    print(f"  → {len(rows)} reviews collected in {elapsed:.1f}s")
    return rows, real_total


def scrape_all(product_url, max_pages=None, polite_delay=0.0,
               multi_pass=False, max_workers=20, batch_size=20):
    """Parallel deep-paginated review scraping.

    Step 1: GET page 1 → extract real `reviewCount` (e.g. 3505).
    Step 2: ceil(reviewCount / 10) → total_pages (e.g. 351).
    Step 3: Split into batches of `batch_size` (default 20) pages.
    Step 4: ThreadPoolExecutor with `max_workers` (default 20) runs them
            concurrently. For ~350 pages: ~18 batches × ~14s wall = ~14s total.
    Step 5: Dedupe by ReviewId and return DataFrame.

    `multi_pass=True` adds a second/third sort-order pass as backstop.
    """
    reviews_url = to_reviews_url(product_url)
    print(f"[info] reviews URL: {reviews_url}")

    seen_ids = set()
    all_rows = []
    total_overall = None

    passes = SORT_PASSES if multi_pass else [("MOST_HELPFUL", "false")]

    for sort_order, cert_buyer in passes:
        rows, total = _scrape_single_pass(
            reviews_url, sort_order, cert_buyer, max_pages, polite_delay,
            max_workers=max_workers, batch_size=batch_size,
        )
        if total_overall is None and total:
            total_overall = total
        new_rows = 0
        for r in rows:
            rid = r.get("ReviewId") or (r.get("Customer Name", "") + "|" + (r.get("Comment", "") or "")[:80])
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            all_rows.append(r)
            new_rows += 1
        print(f"  unique so far: {len(all_rows)}  (this pass added {new_rows})")
        # Early exit: if we've covered the total, stop
        if total_overall and len(all_rows) >= total_overall:
            print(f"[info] full coverage reached — stopping.")
            break

    print(f"[info] FINAL: {len(all_rows)} unique reviews"
          + (f" of ~{total_overall} reported by Flipkart" if total_overall else ""))

    df = pd.DataFrame(all_rows)
    if not df.empty:
        df["VADER Sentiment"] = df["Comment"].apply(
            lambda x: analyzer.polarity_scores(x or "")["compound"]
        )
        df["Label"] = df["VADER Sentiment"].apply(
            lambda s: "Positive" if s > 0.1 else "Negative" if s < -0.1 else "Neutral"
        )
    return df


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else input("Flipkart product URL: ").strip()
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else None

    df = scrape_all(url, max_pages=cap)
    if df.empty:
        print("No reviews scraped.")
        sys.exit(1)

    out = "flipkart_reviews.csv"
    df.to_csv(out, index=False)
    print(f"\n[done] {len(df)} reviews saved to {out}")
    print(df["Label"].value_counts().to_string())
    print("\nAvg rating:", round(df["Rating"].astype(float).mean(), 2))
