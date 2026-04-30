"""
ReviewPulse JSON exporter — schema v2.0.

v2 additions over v1:
  - meta.schema_version = "2.0"; review.date now has iso/days_ago via flexible parser
  - aspects:    per-aspect ABSA (sound, anc, battery, mic, comfort, connectivity,
                build, controls, value) with rating, mentions, sentiment split
  - summary:    heuristic pros / cons via contrastive-conjunction splitting
  - clusters:   complaint clusters (TF-IDF + KMeans on negative sentences)
  - timeseries: monthly buckets (now possible after relative-date fix)
  - geo:        state-level rating + sentiment
  - filters.by_aspect / by_cluster: inverted indexes for new dimensions
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone

import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from analysis_v2 import (
    aggregate_aspects,
    build_geo,
    build_timeseries,
    cluster_complaints,
    extract_pros_cons,
    extract_review_aspects,
    parse_review_date,
)
from scrape_all_reviews import scrape_all

analyzer = SentimentIntensityAnalyzer()

EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\U0001F600-\U0001F64F☀-➿]")

POSITIVE_TITLE_WORDS = {
    "terrific", "great", "best", "worth", "excellent", "wonderful", "mind",
    "brilliant", "awesome", "highly", "perfect", "super", "fabulous",
    "amazing", "classy", "delightful", "fantastic", "good", "nice",
    "value-for-money", "must", "wow", "satisfied", "simply",
}
NEGATIVE_TITLE_WORDS = {
    "waste", "bad", "worst", "poor", "useless", "disappointing",
    "disappointed", "horrible", "terrible", "fake", "trash", "fraud",
    "pathetic", "rubbish", "fail",
}

LOGISTICS_KEYWORDS = {
    "flipkart", "delivery", "deliver", "shipped", "shipping", "package",
    "open box", "open-box", "return", "refund", "warranty", "courier",
    "service", "exchange",
}


def classify_title(title: str) -> str:
    if not title:
        return "unknown"
    t = title.lower()
    if any(w in t for w in NEGATIVE_TITLE_WORDS):
        return "negative_canned"
    if any(w in t for w in POSITIVE_TITLE_WORDS):
        return "positive_canned"
    return "neutral_or_custom"


def length_bucket(n: int) -> str:
    if n < 20:
        return "short"
    if n < 200:
        return "medium"
    return "long"


def has_feature_breakdown(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"[A-Za-z][\w/\- ]{1,40}?[: ]\s*\d{1,2}\s*/\s*10", text))


def is_logistics_only(text: str) -> bool:
    """True if review centers on delivery/return rather than the product."""
    if not text:
        return False
    t = text.lower()
    return any(kw in t for kw in LOGISTICS_KEYWORDS)


def enrich_review(row: dict, scrape_date: datetime | None = None, taxonomy: dict | None = None) -> dict:
    text = row.get("Comment") or ""
    rating = int(row.get("Rating") or 0)
    author = row.get("Customer Name") or ""
    sent_score = analyzer.polarity_scores(text)["compound"]
    sent_label = (
        "positive" if sent_score > 0.1
        else "negative" if sent_score < -0.1
        else "neutral"
    )
    title_cat = classify_title(row.get("Review Title") or "")
    aspect_mentions = extract_review_aspects(text, taxonomy)

    return {
        "id": str(uuid.uuid4()),
        "author": {
            "name": author,
            "is_anonymous": author == "Flipkart Customer",
            "verified": bool(row.get("Verified")),
            "location": {
                "city":  row.get("City") or None,
                "state": row.get("State") or None,
            },
        },
        "rating": rating,
        "title": {
            "text": row.get("Review Title") or "",
            "category": title_cat,
        },
        "comment": {
            "text": text,
            "length": len(text),
            "word_count": len(text.split()),
            "length_bucket": length_bucket(len(text)),
            "has_emoji": bool(EMOJI_RE.search(text)),
            "is_multiline": "\n" in text,
            "has_feature_breakdown": has_feature_breakdown(text),
            "mentions_logistics": is_logistics_only(text),
        },
        "date": parse_review_date(row.get("Date") or "", scrape_date),
        "engagement": {
            "helpful_count": int(row.get("Helpful") or 0),
        },
        "analysis": {
            "sentiment_score": round(sent_score, 4),
            "sentiment_label": sent_label,
            "rating_sentiment_mismatch": (
                (rating >= 4 and sent_label == "negative") or
                (rating <= 2 and sent_label == "positive")
            ),
        },
        "aspect_mentions": aspect_mentions,
        "aspects_present": sorted({h["aspect"] for h in aspect_mentions}),
        "attrs":  row.get("Attrs") or "",
        "images": row.get("Images") or "",
    }


def build_aggregates(reviews):
    n = len(reviews)
    if not n:
        return {}
    ratings = [r["rating"] for r in reviews]
    sentiments = [r["analysis"]["sentiment_label"] for r in reviews]
    cities = [r["author"]["location"]["city"] for r in reviews if r["author"]["location"]["city"]]
    states = [r["author"]["location"]["state"] for r in reviews if r["author"]["location"]["state"]]
    titles = [r["title"]["text"] for r in reviews if r["title"]["text"]]
    buckets = [r["comment"]["length_bucket"] for r in reviews]
    years = [r["date"]["year"] for r in reviews if r["date"]["year"]]
    date_formats = [r["date"]["format"] for r in reviews]

    return {
        "total_reviews": n,
        "average_rating": round(sum(ratings) / n, 2),
        "rating_distribution": dict(sorted(Counter(ratings).items())),
        "sentiment_distribution": dict(Counter(sentiments)),
        "title_categories": dict(Counter(r["title"]["category"] for r in reviews)),
        "top_titles": dict(Counter(titles).most_common(10)),
        "top_cities": dict(Counter(cities).most_common(10)),
        "top_states": dict(Counter(states).most_common(10)),
        "comment_length_buckets": dict(Counter(buckets)),
        "verified_pct": round(
            sum(1 for r in reviews if r["author"]["verified"]) / n * 100, 1
        ),
        "anonymous_pct": round(
            sum(1 for r in reviews if r["author"]["is_anonymous"]) / n * 100, 1
        ),
        "with_emoji": sum(1 for r in reviews if r["comment"]["has_emoji"]),
        "multiline_reviews": sum(1 for r in reviews if r["comment"]["is_multiline"]),
        "feature_breakdown_reviews": sum(
            1 for r in reviews if r["comment"]["has_feature_breakdown"]
        ),
        "rating_sentiment_mismatches": sum(
            1 for r in reviews if r["analysis"]["rating_sentiment_mismatch"]
        ),
        "logistics_mention_count": sum(
            1 for r in reviews if r["comment"]["mentions_logistics"]
        ),
        "year_distribution": dict(sorted(Counter(years).items())),
        "date_format_breakdown": dict(Counter(date_formats)),
    }


def build_filters(reviews):
    out = {
        "by_rating": {},
        "by_sentiment": {},
        "by_title_category": {},
        "by_city": {},
        "by_state": {},
        "by_year": {},
        "by_length_bucket": {},
        "by_aspect": {},
        "with_emoji": [],
        "multiline": [],
        "has_feature_breakdown": [],
        "anonymous": [],
        "rating_sentiment_mismatch": [],
        "logistics": [],
    }
    for r in reviews:
        rid = r["id"]
        out["by_rating"].setdefault(str(r["rating"]), []).append(rid)
        out["by_sentiment"].setdefault(r["analysis"]["sentiment_label"], []).append(rid)
        out["by_title_category"].setdefault(r["title"]["category"], []).append(rid)
        if r["author"]["location"]["city"]:
            out["by_city"].setdefault(r["author"]["location"]["city"], []).append(rid)
        if r["author"]["location"]["state"]:
            out["by_state"].setdefault(r["author"]["location"]["state"], []).append(rid)
        if r["date"]["year"]:
            out["by_year"].setdefault(str(r["date"]["year"]), []).append(rid)
        out["by_length_bucket"].setdefault(r["comment"]["length_bucket"], []).append(rid)
        for a in r["aspects_present"]:
            out["by_aspect"].setdefault(a, []).append(rid)
        if r["comment"]["has_emoji"]:           out["with_emoji"].append(rid)
        if r["comment"]["is_multiline"]:        out["multiline"].append(rid)
        if r["comment"]["has_feature_breakdown"]: out["has_feature_breakdown"].append(rid)
        if r["author"]["is_anonymous"]:         out["anonymous"].append(rid)
        if r["analysis"]["rating_sentiment_mismatch"]: out["rating_sentiment_mismatch"].append(rid)
        if r["comment"]["mentions_logistics"]:  out["logistics"].append(rid)
    return out


def export(product_url, out_path="reviews_analysis.json", df=None):
    if df is None:
        df = scrape_all(product_url)
    if df.empty:
        print("[error] no reviews to export.")
        return None

    scraped_at = datetime.now(timezone.utc)
    reviews = [enrich_review(row, scraped_at) for row in df.to_dict("records")]

    print("[v2] aggregating aspects…")
    aspects = aggregate_aspects(reviews)

    print("[v2] mining pros/cons…")
    summary = extract_pros_cons(reviews)

    print("[v2] clustering complaints…")
    clusters = cluster_complaints(reviews, k=5)

    print("[v2] building timeseries + geo…")
    timeseries = build_timeseries(reviews)
    geo = build_geo(reviews)

    filters = build_filters(reviews)
    filters["by_cluster"] = {c["id"]: c["review_ids"] for c in clusters}

    indexed = {r["id"]: r for r in reviews}

    payload = {
        "meta": {
            "product_url": product_url,
            "scraped_at": scraped_at.isoformat(),
            "schema_version": "2.0",
            "review_count": len(reviews),
        },
        "aggregates": build_aggregates(reviews),
        "aspects":    aspects,
        "summary":    summary,
        "clusters":   clusters,
        "timeseries": timeseries,
        "geo":        geo,
        "filters":    filters,
        "reviews":    indexed,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    print(f"[done] wrote {out_path}  ({len(reviews)} reviews, schema 2.0)")
    return payload


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python export_json.py <flipkart_url> [out.json]")
        sys.exit(1)
    url = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "reviews_analysis.json"

    csv_path = "/Users/sam/Downloads/ReviewPulse-main/flipkart_reviews.csv"
    try:
        df = pd.read_csv(csv_path)
        print(f"[info] reusing existing {csv_path} ({len(df)} rows)")
    except FileNotFoundError:
        df = None

    export(url, out_path=out, df=df)
