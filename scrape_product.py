"""
Product-page scraper for ReviewPulse.

Fetches a Flipkart product page (/p/itm…) and extracts the structured product
data embedded in `window.__INITIAL_STATE__`. Returns a single dict with:

  title, brand, breadcrumb, category (leaf), price, mrp, discount_pct,
  highlights, description, specs (grouped key-value), images,
  variants_available, rating_summary, seller, delivery, qna

The state is one ~1MB JSON blob, so we parse it via a brace-balanced walker
rather than a non-greedy regex.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

from curl_cffi import requests


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def fetch(url: str, retries: int = 3, delay: float = 1.5) -> str | None:
    for attempt in range(retries):
        try:
            r = requests.get(url, impersonate="chrome", timeout=20)
            if r.status_code == 200:
                return r.text
            print(f"  [warn] product page HTTP {r.status_code}")
        except Exception as e:
            print(f"  [warn] {type(e).__name__}: {e}")
        time.sleep(delay * (attempt + 1))
    return None


def extract_initial_state(html: str) -> dict | None:
    """Walk the JSON value of `window.__INITIAL_STATE__ = ...;` with brace
    balancing because the state can be ~1 MB and contain nested `};</script>`."""
    needle = "window.__INITIAL_STATE__ = "
    start = html.find(needle)
    if start < 0:
        return None
    start += len(needle)

    depth = 0
    i = start
    in_str = False
    esc = False
    while i < len(html):
        ch = html[i]
        if esc:
            esc = False
        elif ch == "\\" and in_str:
            esc = True
        elif ch == '"':
            in_str = not in_str
        elif not in_str:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[start:i + 1])
                    except json.JSONDecodeError:
                        return None
        i += 1
    return None


def to_product_url(url: str) -> str:
    """Normalize: if a /product-reviews/ URL was given, convert to /p/."""
    parsed = urlparse(url)
    if "/product-reviews/" in parsed.path:
        parsed = parsed._replace(path=parsed.path.replace("/product-reviews/", "/p/", 1))
    return urlunparse(parsed)


def harvest_texts(obj: Any) -> list[str]:
    """Recursively collect every {"text": "..."} or {"text": [...strings]}."""
    out: list[str] = []
    def walk(o):
        if isinstance(o, dict):
            t = o.get("text")
            if isinstance(t, str):
                out.append(t)
            elif isinstance(t, list):
                for x in t:
                    if isinstance(x, str):
                        out.append(x)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj)
    return out


# ---------------------------------------------------------------------------
# Slot pickers — each finds the slot whose viewType matches the prefix
# ---------------------------------------------------------------------------

def find_slot(slots: list, view_type_prefix: str) -> dict | None:
    for s in slots:
        vt = s.get("slotData", {}).get("widget", {}).get("viewType", "") or ""
        if vt.startswith(view_type_prefix):
            return s.get("slotData", {}).get("widget", {}).get("data", {})
    return None


def find_slot_widget(slots: list, predicate) -> dict | None:
    for s in slots:
        w = s.get("slotData", {}).get("widget", {})
        if predicate(w):
            return w.get("data", {})
    return None


# ---------------------------------------------------------------------------
# Field-specific extractors
# ---------------------------------------------------------------------------

def extract_breadcrumb(slots: list) -> list[str]:
    """Returns the breadcrumb path as a list of category labels."""
    data = find_slot(slots, "breadcrumb")
    if not data:
        return []
    texts = harvest_texts(data)
    crumbs: list[str] = []
    skip_next = False
    for t in texts:
        if t == "/" or t == "Home":
            continue
        if t in crumbs:  # skip duplicates
            continue
        if len(t) > 80:  # final long product title — break
            break
        crumbs.append(t)
    return crumbs


def extract_title(slots: list, breadcrumb: list[str], specs: dict | None = None) -> dict:
    """Find the longest text string in the title slot — that's the full title.
    Brand prefers spec lookup, else falls back to first word."""
    data = find_slot(slots, "default_fk_pp_productTitle")
    full = ""
    if data:
        # `prependingText` is where Flipkart stores the full title for "more" expander
        def walk(o):
            nonlocal full
            if isinstance(o, dict):
                pp = o.get("prependingText")
                if isinstance(pp, str) and len(pp) > len(full):
                    full = pp
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(data)
        if not full:
            for t in harvest_texts(data):
                if len(t) > len(full) and len(t) > 20:
                    full = t

    brand = ""
    if specs:
        for grp in specs.values():
            for k, v in grp.items():
                if k.lower() == "brand":
                    brand = v
                    break
            if brand: break
    if not brand and full:
        brand = full.split()[0]
    title = full or (breadcrumb[-1] if breadcrumb else "")
    return {"brand": brand, "title": title, "full_text": full}


_PRICE_PRECISE_RE = re.compile(r"^\s*₹\s*([\d,]{2,})\s*$")


def extract_pricing(slots: list) -> dict:
    """Find final price, MRP, discount %. Only counts standalone ₹X,XXX strings —
    avoids spurious matches like "₹21478744 saved" which is a counter, not a price.
    """
    data = find_slot(slots, "pp_pricing_price_summary")
    if not data:
        return {"final_price": None, "mrp": None, "discount_pct": None,
                "currency": "INR", "raw": []}
    texts = harvest_texts(data)
    prices: list[int] = []
    for t in texts:
        m = _PRICE_PRECISE_RE.match(t)
        if not m:
            continue
        try:
            v = int(m.group(1).replace(",", ""))
            if 50 <= v <= 5_000_000:  # plausible Indian retail range
                prices.append(v)
        except ValueError:
            pass

    discount: int | None = None
    for t in texts:
        m = re.match(r"^\s*(\d{1,2})\s*%\s*$", t)
        if m:
            try:
                v = int(m.group(1))
                if 1 <= v <= 99:
                    discount = v
                    break
            except ValueError:
                pass

    final = min(prices) if prices else None
    mrp   = max(prices) if prices and max(prices) > (final or 0) else None
    return {
        "final_price":  final,
        "mrp":          mrp,
        "discount_pct": discount,
        "currency":     "INR",
        "raw":          texts[:10],
    }


def extract_rating_summary(slots: list) -> dict:
    """Average rating + total ratings from the rating widget."""
    data = find_slot(slots, "default_fk_pp_multimedia_rating_clone")
    if not data:
        return {}
    texts = harvest_texts(data)
    rating: float | None = None
    ratings_count: int | None = None
    reviews_count: int | None = None
    for t in texts:
        m = re.match(r"^\s*(\d\.\d)\s*$", t)
        if m and rating is None:
            rating = float(m.group(1))
        m = re.search(r"([\d,]+)\s*Ratings?", t)
        if m:
            try:
                ratings_count = int(m.group(1).replace(",", ""))
            except ValueError:
                pass
        m = re.search(r"([\d,]+)\s*Reviews?", t)
        if m:
            try:
                reviews_count = int(m.group(1).replace(",", ""))
            except ValueError:
                pass
    return {"rating": rating, "ratings_count": ratings_count,
            "reviews_count": reviews_count}


def extract_highlights(slots: list) -> list[str]:
    """Bullet-point feature highlights."""
    data = find_slot(slots, "product-highlights-layout")
    if not data:
        return []
    texts = harvest_texts(data)
    seen: set[str] = set()
    out: list[str] = []
    for t in texts:
        clean = t.strip()
        if (len(clean) < 6 or len(clean) > 160 or clean in seen
                or clean.lower() in ("product highlights",
                                     "key product attributes and feature details")):
            continue
        seen.add(clean)
        out.append(clean)
    return out[:14]


def extract_specs(slots: list) -> dict[str, dict[str, str]]:
    """Group → key → value. Walks the spec list slot via label_0/label_1 pairs."""
    data = find_slot(slots, "rpd_all_details_showcase_vertical_list_layout")
    if not data:
        return {}

    pairs: list[tuple[str, str]] = []

    def walk(o):
        if isinstance(o, dict):
            l0 = o.get("label_0", {}).get("value", {}).get("text") if isinstance(o.get("label_0"), dict) else None
            l1 = o.get("label_1", {}).get("value", {}).get("text") if isinstance(o.get("label_1"), dict) else None
            l2 = o.get("label_2", {}).get("value", {}).get("text") if isinstance(o.get("label_2"), dict) else None
            value = l1 or l2
            if isinstance(l0, str) and value is not None and 0 < len(l0) < 80:
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value)
                value = str(value).strip()
                if value and value != l0:
                    pairs.append((l0.strip(), value))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    seen: set[tuple[str, str]] = set()
    grouped: dict[str, dict[str, str]] = {"General": {}}
    for k, v in pairs:
        if (k, v) in seen:
            continue
        seen.add((k, v))
        if k.lower() in {"product highlights", "view all"}:
            continue
        grouped["General"][k] = v
    if not grouped["General"]:
        del grouped["General"]
    return grouped


def extract_description(slots: list) -> str:
    """Long product description (often present at top of specs widget)."""
    data = find_slot(slots, "rpd_all_details_showcase_vertical_list_layout")
    if not data:
        return ""
    texts = harvest_texts(data)
    long_texts = [t for t in texts if len(t) > 120]
    return long_texts[0] if long_texts else ""


def extract_images(slots: list) -> list[str]:
    """Image URLs from the multimedia slider slot."""
    data = find_slot(slots, "default_fk_pp_multimedia_inline_slider")
    urls: list[str] = []
    if not data:
        return urls

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("dynamicImageUrl", "imageUrl", "url") and isinstance(v, str):
                    if "rukminim" in v or "image" in v.lower():
                        urls.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        # Replace placeholder template params {@width} {@height} {@quality}
        u = u.replace("{@width}", "832").replace("{@height}", "832").replace("{@quality}", "80")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:10]


def extract_variants(slots: list) -> list[dict]:
    """Available variants (color, size, etc.) with their PIDs/labels."""
    data = find_slot(slots, "variant-selector")
    if not data:
        return []
    variants: list[dict] = []
    seen: set[str] = set()

    def walk(o):
        if isinstance(o, dict):
            label = None
            if "label_0" in o and isinstance(o["label_0"], dict):
                label = o["label_0"].get("value", {}).get("text")
            if isinstance(label, str) and 1 < len(label) < 40 and label not in seen:
                seen.add(label)
                variants.append({"value": label})
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return variants[:8]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_product_page(url: str) -> dict:
    """Single function — paste any /p/ URL, get a structured dict."""
    url = to_product_url(url)
    print(f"[product] fetching {url[:100]}…")
    html = fetch(url)
    if not html:
        return {"error": "Failed to fetch product page"}

    state = extract_initial_state(html)
    if not state:
        return {"error": "Could not parse product page state"}

    slots = state.get("multiWidgetState", {}).get("widgetsData", {}).get("slots", [])
    if not slots:
        return {"error": "Empty page state"}

    breadcrumb = extract_breadcrumb(slots)
    specs      = extract_specs(slots)
    title_obj  = extract_title(slots, breadcrumb, specs)
    price      = extract_pricing(slots)
    rating     = extract_rating_summary(slots)
    highlights = extract_highlights(slots)
    description = extract_description(slots)
    images     = extract_images(slots)
    variants   = extract_variants(slots)

    return {
        "url":        url,
        "breadcrumb": breadcrumb,
        "category":   breadcrumb[-1] if breadcrumb else None,
        "category_path": " / ".join(breadcrumb) if breadcrumb else None,
        "brand":      title_obj["brand"],
        "title":      title_obj["title"] or (breadcrumb[-1] if breadcrumb else ""),
        "pricing":    price,
        "rating":     rating,
        "highlights": highlights,
        "specs":      specs,
        "description": description,
        "images":     images,
        "variants":   variants,
    }


if __name__ == "__main__":
    import sys
    test_url = sys.argv[1] if len(sys.argv) > 1 else \
        "https://www.flipkart.com/oneplus-buds-3-tws-ear-earbuds-sliding-volume-control-49db-anc-bluetooth-gaming/p/itm3f89e2c2d7b10?pid=ACCGWVFAJHJAGHYG"
    result = scrape_product_page(test_url)
    print(json.dumps(result, indent=2, ensure_ascii=False)[:4000])
