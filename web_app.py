"""ReviewPulse — Flask app. Now scrapes product page + reviews and renders
dynamically based on what the product actually exposes."""

from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request

from analysis_v2 import (
    aggregate_aspects,
    align_specs_with_aspects,
    build_geo,
    build_timeseries,
    cluster_complaints,
    compute_certified_split,
    compute_forensics,
    compute_logistics_split,
    compute_one_star_complaints,
    compute_photos,
    compute_reviewer_profile,
    compute_use_cases,
    compute_variants,
    compute_verdict,
    compute_who_should_buy,
    extract_pros_cons,
    find_reviewer_surprises,
)
from category_taxonomies import (
    CATEGORIES, aspects_for, city_tier, detect_category, use_cases_for,
)
from export_json import build_aggregates, build_filters, enrich_review
from scrape_all_reviews import scrape_all
from scrape_product import scrape_product_page

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    body = request.get_json(silent=True) or {}
    url = body.get("url", "").strip()
    max_pages = body.get("max_pages")

    if not url or "flipkart.com" not in url:
        return jsonify({"error": "Please provide a valid Flipkart product URL."}), 400

    # 1) Product page → title, brand, breadcrumb, specs, price, images, …
    print("[pipeline] scraping product page…")
    product = scrape_product_page(url)
    if "error" in product:
        product = {}  # tolerable — fall back to URL-derived metadata

    # Use breadcrumb as primary category signal (more accurate than URL keywords)
    category_signal = " ".join(product.get("breadcrumb") or []) + " " + product.get("title", "")

    # 2) Reviews
    print("[pipeline] scraping reviews…")
    try:
        df = scrape_all(url, max_pages=max_pages)
    except Exception as e:
        return jsonify({"error": f"Scrape failed: {e}"}), 500
    if df.empty:
        return jsonify({"error": "No reviews found for this product."}), 404

    sample_text = " ".join(df["Comment"].fillna("").head(20).astype(str).tolist())
    category_key = detect_category(url=url,
                                   title=category_signal,
                                   sample_text=sample_text)
    taxonomy = aspects_for(category_key)
    cat_meta = {
        "key":           category_key,
        "label":         CATEGORIES[category_key]["label"],
        "breadcrumb":    product.get("breadcrumb", []),
        "category_path": product.get("category_path"),
        "aspect_labels": {k: a["label"] for k, a in taxonomy.items()},
        "aspect_icons":  {k: a["icon"]  for k, a in taxonomy.items()},
    }

    # 3) Enrich + analyze
    scraped_at = datetime.now(timezone.utc)
    reviews = [enrich_review(row, scraped_at, taxonomy) for row in df.to_dict("records")]

    aggregates = build_aggregates(reviews)
    aspects    = aggregate_aspects(reviews, taxonomy)
    summary    = extract_pros_cons(reviews)
    clusters   = cluster_complaints(reviews, k=5, taxonomy_aspects=taxonomy, aspects=aspects)
    timeseries = build_timeseries(reviews)
    geo        = build_geo(reviews)

    cert_split   = compute_certified_split(reviews)
    forensics    = compute_forensics(reviews)
    logistics    = compute_logistics_split(reviews, aspects)
    verdict      = compute_verdict(aspects, aggregates)
    who_buy      = compute_who_should_buy(aspects, aggregates)
    one_star     = compute_one_star_complaints(reviews, clusters)
    variants     = compute_variants(reviews)
    photos       = compute_photos(reviews)
    spec_align   = align_specs_with_aspects(product, aspects)
    surprises    = find_reviewer_surprises(product, aspects, taxonomy)
    use_cases    = compute_use_cases(reviews, use_cases_for(category_key))
    reviewer_profile = compute_reviewer_profile(reviews, city_tier)

    filters = build_filters(reviews)
    filters["by_cluster"] = {c["id"]: c["review_ids"] for c in clusters}

    trust = {"score": forensics["score"], "risk": forensics["risk"]}

    return jsonify({
        "meta": {
            "product_url":    url,
            "scraped_at":     scraped_at.isoformat(),
            "schema_version": "4.0",
            "review_count":   len(reviews),
        },
        "product":            product,
        "category":           cat_meta,
        "spec_alignment":     spec_align,
        "reviewer_surprises": surprises,
        "aggregates":         aggregates,
        "aspects":            aspects,
        "summary":            summary,
        "clusters":           clusters,
        "timeseries":         timeseries,
        "geo":                geo,
        "cert_split":         cert_split,
        "forensics":          forensics,
        "logistics_split":    logistics,
        "use_cases":          use_cases,
        "reviewer_profile":   reviewer_profile,
        "verdict":            verdict,
        "who_should_buy":     who_buy,
        "one_star_complaints": one_star,
        "variants":           variants,
        "photos":             photos,
        "trust":              trust,
        "filters":            filters,
        "reviews":            {r["id"]: r for r in reviews},
    })


if __name__ == "__main__":
    app.run(debug=True, port=5050)
