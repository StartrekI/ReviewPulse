"""
Phase 1 analysis pipeline for ReviewPulse v2.

Adds four foundation capabilities on top of the existing enrichment:
  1. Flexible date parser (handles "Feb, 2024", "10 months ago", "17 days ago")
  2. Aspect-Based Sentiment Analysis across 9 product dimensions
  3. Pros/cons mining via contrastive conjunction splitting
  4. Complaint clustering via TF-IDF + KMeans on negative-leaning sentences

Designed to plug into export_json.py without breaking the v1 schema.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import dateparser
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

_MONTH_YEAR_RE = re.compile(r"^([A-Za-z]{3,9}),?\s*(\d{4})$")
_RELATIVE_RE = re.compile(r"^(\d+)\s+(day|days|month|months|year|years|hour|hours|week|weeks)\s+ago$", re.I)


def parse_review_date(raw: str, scrape_date: datetime | None = None) -> dict:
    """Robust parser for Flipkart's mixed date formats.

    Returns {raw, iso, month, year, days_ago, format} where iso is YYYY-MM-DD
    or None if unparseable. `scrape_date` anchors relative dates; defaults to now.
    """
    if not raw or not isinstance(raw, str):
        return {"raw": raw, "iso": None, "month": None, "year": None,
                "days_ago": None, "format": "missing"}

    anchor = scrape_date or datetime.now(timezone.utc)
    s = raw.strip()

    m = _MONTH_YEAR_RE.match(s)
    if m:
        try:
            dt = datetime.strptime(f"{m.group(1)[:3]} 15 {m.group(2)}", "%b %d %Y")
            dt = dt.replace(tzinfo=timezone.utc)
            return {
                "raw": raw,
                "iso": dt.date().isoformat(),
                "month": dt.strftime("%b"),
                "year": dt.year,
                "days_ago": (anchor - dt).days,
                "format": "month_year",
            }
        except ValueError:
            pass

    m = _RELATIVE_RE.match(s)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        delta_days = {
            "hour": 0, "hours": 0,
            "day": n, "days": n,
            "week": n * 7, "weeks": n * 7,
            "month": n * 30, "months": n * 30,
            "year": n * 365, "years": n * 365,
        }[unit]
        dt = anchor - timedelta(days=delta_days)
        return {
            "raw": raw,
            "iso": dt.date().isoformat(),
            "month": dt.strftime("%b"),
            "year": dt.year,
            "days_ago": delta_days,
            "format": "relative",
        }

    parsed = dateparser.parse(s, settings={"RELATIVE_BASE": anchor.replace(tzinfo=None)})
    if parsed:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return {
            "raw": raw,
            "iso": parsed.date().isoformat(),
            "month": parsed.strftime("%b"),
            "year": parsed.year,
            "days_ago": (anchor - parsed).days,
            "format": "fallback",
        }

    return {"raw": raw, "iso": None, "month": None, "year": None,
            "days_ago": None, "format": "unparseable"}


# ---------------------------------------------------------------------------
# Aspect taxonomy & ABSA
# ---------------------------------------------------------------------------

ASPECTS: dict[str, list[str]] = {
    "sound":        ["sound", "audio", "music", "bass", "treble", "high",
                     "low", "clarity", "loudness", "volume", "stereo",
                     "muddy", "crisp", "tinny", "acoustic"],
    "anc":          ["anc", "noise cancel", "noise cancellation", "noise cancelling",
                     "active noise", "noise reduction", "ambient"],
    "battery":      ["battery", "charge", "charging", "playback", "backup",
                     "lasting", "drain", "hours of"],
    "mic":          ["mic", "microphone", "call quality", "calls", "voice",
                     "khar khar", "distortion during call"],
    "comfort":      ["comfort", "fit", "ear tip", "ear-tip", "headache",
                     "pressure", "uncomfortable", "snug", "slipping"],
    "connectivity": ["bluetooth", "connect", "pairing", "multipoint",
                     "switching", "lag", "latency", "dropout", "delay"],
    "build":        ["build", "design", "looks", "premium look", "case",
                     "material", "durable", "sturdy", "cheap feel"],
    "controls":     ["touch", "tap", "gesture", "button", "swipe", "control",
                     "volume control"],
    "value":        ["price", "value", "money", "worth", "cost", "expensive",
                     "cheap", "budget", "vfm", "overpriced"],
}

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text)]
    return [p for p in parts if p]


def detect_aspects(sentence: str, taxonomy: dict | None = None) -> list[str]:
    """Returns aspect labels matched in this sentence (lowercased keyword match).

    If `taxonomy` is provided (per-category), uses its aspects/keywords;
    otherwise falls back to the default ASPECTS dict.
    """
    s = sentence.lower()
    if taxonomy:
        hits = []
        for key, asp in taxonomy.items():
            if any(kw in s for kw in asp["keywords"]):
                hits.append(key)
        return hits
    return [a for a, kws in ASPECTS.items() if any(kw in s for kw in kws)]


def score_sentence(sentence: str) -> tuple[float, str]:
    score = analyzer.polarity_scores(sentence)["compound"]
    label = "positive" if score > 0.1 else "negative" if score < -0.1 else "neutral"
    return score, label


def extract_review_aspects(text: str, taxonomy: dict | None = None) -> list[dict]:
    """For each sentence in the review, return aspect mentions + sentiment."""
    out = []
    for sent in split_sentences(text):
        aspects = detect_aspects(sent, taxonomy)
        if not aspects:
            continue
        score, label = score_sentence(sent)
        for a in aspects:
            out.append({"aspect": a, "sentence": sent,
                        "sentiment_score": round(score, 4),
                        "sentiment_label": label})
    return out


def aggregate_aspects(reviews: list[dict], taxonomy: dict | None = None) -> dict[str, dict]:
    """Roll per-review aspect mentions into per-aspect aggregates.

    If `taxonomy` is given, only those aspect keys are included; otherwise
    the legacy ASPECTS dict drives the rollup.
    """
    keys = list(taxonomy.keys()) if taxonomy else list(ASPECTS.keys())
    agg: dict[str, dict] = {a: {"mention_reviews": set(), "sentences": [],
                                "review_ratings": [], "review_ids": []}
                            for a in keys}

    for r in reviews:
        rid = r["id"]
        rating = r["rating"]
        for hit in r["aspect_mentions"]:
            a = hit["aspect"]
            if a not in agg:
                continue
            agg[a]["mention_reviews"].add(rid)
            agg[a]["sentences"].append(hit["sentiment_label"])
            if rid not in agg[a]["review_ids"]:
                agg[a]["review_ids"].append(rid)
                agg[a]["review_ratings"].append(rating)

    out: dict[str, dict] = {}
    for a, d in agg.items():
        n_sent = len(d["sentences"])
        if n_sent == 0:
            out[a] = {"mentions": 0, "rating": None, "sentences": 0,
                      "pos": 0, "neu": 0, "neg": 0, "pos_pct": 0.0,
                      "polarizing": False, "review_ids": []}
            continue
        c = Counter(d["sentences"])
        pos, neu, neg = c.get("positive", 0), c.get("neutral", 0), c.get("negative", 0)
        pos_pct = pos / n_sent
        neg_pct = neg / n_sent
        rating_avg = sum(d["review_ratings"]) / len(d["review_ratings"])
        out[a] = {
            "mentions":   len(d["mention_reviews"]),
            "rating":     round(rating_avg, 2),
            "sentences":  n_sent,
            "pos":        pos,
            "neu":        neu,
            "neg":        neg,
            "pos_pct":    round(pos_pct, 3),
            "neg_pct":    round(neg_pct, 3),
            "polarizing": pos_pct >= 0.3 and neg_pct >= 0.2,
            "review_ids": d["review_ids"],
        }
    return out


# ---------------------------------------------------------------------------
# Pros / cons mining
# ---------------------------------------------------------------------------

_CONTRASTIVE_RE = re.compile(
    r"\b(but|however|although|though|except|whereas|yet)\b",
    re.IGNORECASE,
)
_STOPWORDS = {
    "the","is","a","an","and","or","of","in","on","for","to","with","this",
    "that","it","its","i","my","me","you","your","we","they","them","very",
    "so","such","also","too","just","really","quite","more","most","much",
    "be","been","was","were","are","am","have","has","had","not","no",
    "do","does","did","will","would","can","could","should","at","by","as",
    "if","then","than","when","while","one","two","get","got","go","good",
    "but","however","although","though","whereas","yet","product","item",
}


def extract_phrases(text: str, n: int = 3) -> list[str]:
    """Extract candidate noun-phrase-ish bigrams/trigrams."""
    words = re.findall(r"[A-Za-z][A-Za-z\-']{1,}", text.lower())
    words = [w for w in words if w not in _STOPWORDS and len(w) > 2]
    grams = []
    for size in (3, 2):
        grams += [" ".join(words[i:i+size]) for i in range(len(words) - size + 1)]
    return grams[:n]


def extract_pros_cons(reviews: list[dict], top_k: int = 12) -> dict:
    """Split reviews on contrastive conjunctions; collect phrases per side.

    Heuristic: in a review with overall positive rating that contains 'but',
    the clause AFTER 'but' is typically the con. Inverse for negative reviews.
    """
    pros_phrases: list[tuple[str, str]] = []
    cons_phrases: list[tuple[str, str]] = []

    for r in reviews:
        text = r["comment"]["text"]
        rating = r["rating"]
        rid = r["id"]
        if not text:
            continue

        match = _CONTRASTIVE_RE.search(text)
        if match:
            left = text[:match.start()].strip()
            right = text[match.end():].strip()
            if rating >= 4:
                for p in extract_phrases(left):  pros_phrases.append((p, rid))
                for p in extract_phrases(right): cons_phrases.append((p, rid))
            elif rating <= 2:
                for p in extract_phrases(left):  cons_phrases.append((p, rid))
                for p in extract_phrases(right): pros_phrases.append((p, rid))
            else:
                _, label = score_sentence(left)
                if label == "positive":
                    for p in extract_phrases(left):  pros_phrases.append((p, rid))
                    for p in extract_phrases(right): cons_phrases.append((p, rid))
                else:
                    for p in extract_phrases(left):  cons_phrases.append((p, rid))
                    for p in extract_phrases(right): pros_phrases.append((p, rid))
        else:
            score = r["analysis"]["sentiment_score"]
            if rating >= 4 and score > 0.2:
                for p in extract_phrases(text): pros_phrases.append((p, rid))
            elif rating <= 2 or score < -0.2:
                for p in extract_phrases(text): cons_phrases.append((p, rid))

    def _top(pairs):
        by_phrase: dict[str, list[str]] = defaultdict(list)
        for phrase, rid in pairs:
            by_phrase[phrase].append(rid)
        ranked = sorted(by_phrase.items(), key=lambda kv: -len(kv[1]))
        return [
            {"phrase": ph, "count": len(set(rids)), "review_ids": list(set(rids))[:8]}
            for ph, rids in ranked if len(set(rids)) >= 2
        ][:top_k]

    return {"pros": _top(pros_phrases), "cons": _top(cons_phrases)}


# ---------------------------------------------------------------------------
# Complaint clustering
# ---------------------------------------------------------------------------

def collect_negative_sentences(reviews: list[dict]) -> list[tuple[str, str, int]]:
    """Returns (sentence, review_id, rating) for negatively-toned sentences."""
    out = []
    for r in reviews:
        if r["rating"] > 3 and r["analysis"]["sentiment_label"] != "negative":
            continue
        for sent in split_sentences(r["comment"]["text"]):
            if len(sent) < 12:
                continue
            score, label = score_sentence(sent)
            if label == "negative" or (r["rating"] <= 2 and label != "positive"):
                out.append((sent, r["id"], r["rating"]))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Hand-curated complaint archetypes — high-precision regex patterns
# These cover the most common Flipkart-specific failure modes across all
# product categories. Order matters: more specific first.
# ─────────────────────────────────────────────────────────────────────────────
COMPLAINT_PATTERNS = {
    "defective_on_arrival": {
        "label":       "Defective on arrival",
        "icon":        "shield",
        "category":    "Quality",
        "description": "Product was broken or non-functional out of the box",
        "patterns": [
            r"\b(stopped\s+working|not\s+working|doesn'?t\s+work|didn'?t\s+work|never\s+worked)\b",
            r"\b(dead\s+on\s+arrival|doa|faulty\s+from)\b",
            r"\b(received|got|opened)\b[^.!?]{0,40}\b(broken|damaged|defective|faulty|not\s+working)\b",
            r"\b(broken|damaged|defective|faulty)\b[^.!?]{0,40}\b(received|delivered|arrived|first\s+day)\b",
        ],
    },
    "open_box_damage": {
        "label":       "Open-box / delivery damage",
        "icon":        "bag",
        "category":    "Logistics",
        "description": "Received damaged, packaging tampered, or seal broken",
        "patterns": [
            r"\bopen[\s-]?box\b[^.!?]{0,40}\b(damage|broken|missing|defect)\b",
            r"\b(seal|packaging)\b[^.!?]{0,30}\b(broken|tampered|damaged|opened)\b",
            r"\b(damaged|broken)\b[^.!?]{0,30}\b(delivery|courier|shipping|packaging|box)\b",
        ],
    },
    "missing_items": {
        "label":       "Missing accessories",
        "icon":        "bag",
        "category":    "Logistics",
        "description": "Charger, cable, tips, manual, or other items not in box",
        "patterns": [
            r"\b(missing|didn'?t\s+(get|receive)|not\s+(got|received))\b[^.!?]{0,40}\b(charger|cable|tip|manual|warranty\s+card|earbud|adapter|sim|box|item|accessory)\b",
            r"\b(empty\s+box|incomplete\s+package|partial\s+order)\b",
        ],
    },
    "fake_product": {
        "label":       "Authenticity concerns",
        "icon":        "shield",
        "category":    "Trust",
        "description": "Reviewer suspects fake, duplicate, or counterfeit product",
        "patterns": [
            r"\b(fake|duplicate|counterfeit|not\s+original|not\s+genuine|first[\s-]?copy)\b",
            r"\b(replica|copy|cloned|spurious|knock[\s-]?off)\b",
        ],
    },
    "misleading_advertising": {
        "label":       "Misleading specs / claims",
        "icon":        "spark",
        "category":    "Trust",
        "description": "Product doesn't match advertised specs or images",
        "patterns": [
            r"\b(misleading|false|fake|different\s+from|not\s+as)\b[^.!?]{0,30}\b(advertise|description|spec|claim|promise|shown|expected|picture|image)\b",
            r"\b(not\s+as\s+(advertised|shown|described|expected|promised|pictured))\b",
            r"\bcheated\b|\bcheating\b",
        ],
    },
    "battery_degradation": {
        "label":       "Battery degradation",
        "icon":        "battery",
        "category":    "Reliability",
        "description": "Battery life dropped sharply after weeks/months of use",
        "patterns": [
            r"\b(battery)\b[^.!?]{0,40}\b(drain|drop|degrad|dying|reduced|weaker|poor|short|less|half)\b",
            r"\b(after|within)\b[^.!?]{0,20}\b(months?|weeks?|year)\b[^.!?]{0,40}\b(battery|charge)\b",
            r"\b(battery\s+life)\b[^.!?]{0,30}\b(decreased|reduced|worse|short|bad|poor)\b",
            r"\b(charge|battery)\b[^.!?]{0,30}\b(drains?\s+(fast|quick|in\s+\d))\b",
        ],
    },
    "noise_artifacts": {
        "label":       "Noise / distortion / static",
        "icon":        "speaker",
        "category":    "Audio",
        "description": "Hearable static, crackling, hiss, or distortion in audio",
        "patterns": [
            r"\b(static|distortion|crackl|crackel|hiss|buzz|hum|popping|cutting|cracking)\b",
            r"\b(khar\s+khar|distorted|muffled|garbled|tinny\s+sound)\b",
        ],
    },
    "connectivity_drops": {
        "label":       "Connectivity / Bluetooth drops",
        "icon":        "wifi",
        "category":    "Connectivity",
        "description": "Frequent disconnects, pairing failures, lag",
        "patterns": [
            r"\b(disconnect|drop\s+connection|lose\s+connection|connection\s+(drop|lost|cuts))\b",
            r"\b(pairing|bluetooth)\b[^.!?]{0,30}\b(issue|problem|fail|won'?t|not\s+work|trouble)\b",
            r"\b(lag|latency|delay)\b[^.!?]{0,30}\b(audio|video|sound|game)\b",
        ],
    },
    "fit_comfort_issue": {
        "label":       "Fit / comfort problems",
        "icon":        "diamond",
        "category":    "Comfort",
        "description": "Doesn't fit, uncomfortable, falls out, or causes pain",
        "patterns": [
            r"\b(doesn'?t|don'?t|not)\s+(fit|stay|sit)\b",
            r"\b(too\s+(tight|loose|small|big|large|narrow|wide))\b",
            r"\b(uncomfortable|hurt|pain|sore|ache)\b[^.!?]{0,30}\b(ear|fit|wear|use)\b",
            r"\b(falls?|slips?|keeps?\s+falling)\s+out\b",
        ],
    },
    "warranty_support": {
        "label":       "Warranty / service issues",
        "icon":        "shield",
        "category":    "Support",
        "description": "Customer support unresponsive, replacement denied, etc.",
        "patterns": [
            r"\b(warranty|service|support|replacement|return)\b[^.!?]{0,40}\b(no|not|denied|refused|delayed|slow|poor|terrible|bad|worst)\b",
            r"\b(no\s+(response|support|reply|help))\b",
            r"\b(brand|seller)\b[^.!?]{0,30}\b(unresponsive|ignoring|no\s+reply)\b",
        ],
    },
    "size_mismatch": {
        "label":       "Size / measurement mismatch",
        "icon":        "ruler",
        "category":    "Fit",
        "description": "Size received didn't match what was ordered or expected",
        "patterns": [
            r"\b(size|measurement)\b[^.!?]{0,30}\b(wrong|different|mismatch|incorrect|small|large|tight|loose)\b",
            r"\bordered\s+\w+\s+got\b",
            r"\b(received|got)\b[^.!?]{0,20}\b(different\s+size|wrong\s+size)\b",
        ],
    },
    "color_mismatch": {
        "label":       "Color / appearance mismatch",
        "icon":        "drop",
        "category":    "Quality",
        "description": "Color, finish, or appearance differs from listing",
        "patterns": [
            r"\bcolou?r\b[^.!?]{0,30}\b(different|wrong|fade|fading|not\s+as)\b",
            r"\b(picture|image|photo)\b[^.!?]{0,20}\b(different|misleading)\b",
        ],
    },
}


def _detect_pattern_clusters(reviews):
    """Pattern-archetype detection — high-precision regex matching."""
    clusters = []
    consumed_review_ids = set()

    for key, pat in COMPLAINT_PATTERNS.items():
        matched = []
        sample_phrases: list[str] = []
        for r in reviews:
            text = r["comment"]["text"] or ""
            for p in pat["patterns"]:
                m = re.search(p, text, re.IGNORECASE)
                if not m:
                    continue
                matched.append(r)
                if len(sample_phrases) < 4:
                    idx = m.start()
                    snippet = text[max(0, idx - 25): min(len(text), idx + 70)]
                    snippet = re.sub(r"\s+", " ", snippet).strip(" .,;:")
                    if snippet and snippet not in sample_phrases:
                        sample_phrases.append(snippet)
                break  # one match per review per pattern
        if len(matched) < 3:
            continue
        consumed_review_ids.update(r["id"] for r in matched)
        clusters.append(_build_cluster(
            key, pat["label"], pat["icon"], pat["category"], pat["description"],
            "pattern", matched, sample_phrases,
        ))
    return clusters, consumed_review_ids


def _detect_aspect_clusters(reviews, aspects, taxonomy_aspects, consumed_ids):
    """For each aspect with a meaningful negative slice, create a sub-cluster
    of reviews where that aspect appears in negative context.
    Skips reviews already consumed by pattern clusters."""
    if not aspects:
        return []

    asp_clusters = []
    for aspect_key, agg in aspects.items():
        if agg["mentions"] < 5 or agg["neg"] < 3:
            continue
        # Only if neg is a meaningful share
        total = agg["pos"] + agg["neu"] + agg["neg"] or 1
        if agg["neg"] / total < 0.20:
            continue

        meta = (taxonomy_aspects or {}).get(aspect_key, {})
        label = meta.get("label", aspect_key.title())
        icon = meta.get("icon", "spark")

        # Find reviews with this aspect mentioned negatively
        matched = []
        sample_phrases = []
        for r in reviews:
            if r["id"] in consumed_ids:
                continue
            negative_aspect_sents = [
                m for m in r.get("aspect_mentions", [])
                if m["aspect"] == aspect_key and m["sentiment_label"] == "negative"
            ]
            if not negative_aspect_sents:
                continue
            matched.append(r)
            if len(sample_phrases) < 4:
                snippet = re.sub(r"\s+", " ", negative_aspect_sents[0]["sentence"]).strip()[:90]
                if snippet and snippet not in sample_phrases:
                    sample_phrases.append(snippet)

        if len(matched) < 3:
            continue
        consumed_ids.update(r["id"] for r in matched)
        asp_clusters.append(_build_cluster(
            f"aspect_{aspect_key}",
            f"{label} — recurring complaint",
            icon,
            "Aspect",
            f"Reviews where {label.lower()} was discussed negatively",
            "aspect",
            matched,
            sample_phrases,
        ))
    return asp_clusters


def _detect_kmeans_residual(reviews, consumed_ids, k=3):
    """Catch-all KMeans on negative reviews not covered by patterns/aspects."""
    leftover = [r for r in reviews
                if r["id"] not in consumed_ids
                and (r["rating"] <= 2 or r["analysis"]["sentiment_label"] == "negative")]
    if len(leftover) < k * 2:
        return []

    texts = [(r["comment"]["text"] or "")[:600] for r in leftover]
    vec = TfidfVectorizer(ngram_range=(1, 2), max_df=0.85, min_df=2,
                          stop_words="english", max_features=1500)
    try:
        X = vec.fit_transform(texts)
    except ValueError:
        return []
    if X.shape[0] < k or X.shape[1] < k:
        k = max(2, min(X.shape[0] - 1, X.shape[1] - 1, k))
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(X)
    terms = vec.get_feature_names_out()

    out = []
    for cid in range(k):
        members = [leftover[i] for i, lab in enumerate(labels) if lab == cid]
        if len(members) < 3:
            continue
        center = km.cluster_centers_[cid]
        top_term_idx = center.argsort()[::-1][:4]
        label_terms = [terms[i] for i in top_term_idx if center[i] > 0]
        label = " / ".join(label_terms[:2]).title() or "Other complaints"
        sample_phrases = [
            re.sub(r"\s+", " ", (m["comment"]["text"] or ""))[:90]
            for m in members[:3]
        ]
        out.append(_build_cluster(
            f"residual_{cid}", label, "spark", "Other",
            "Auto-discovered cluster from remaining negative reviews",
            "residual", members, sample_phrases,
        ))
    return out


def _build_cluster(cid, label, icon, category, description, ctype,
                   matched_reviews, sample_phrases):
    """Compute the rich stats payload for a cluster."""
    n = len(matched_reviews)
    ratings = [r["rating"] for r in matched_reviews]
    avg_rating = sum(ratings) / n if n else 0
    helpful = sum(r["engagement"]["helpful_count"] for r in matched_reviews)
    verified = sum(1 for r in matched_reviews if r["author"]["verified"])

    # Trend: most-recent half vs older half by days_ago
    dated = [r for r in matched_reviews if r["date"].get("days_ago") is not None]
    trend_pct = 0
    if len(dated) >= 4:
        dated.sort(key=lambda r: r["date"]["days_ago"])
        half = len(dated) // 2
        recent = dated[:half]
        older = dated[half:]
        rec_per_day = len(recent) / max(recent[-1]["date"]["days_ago"], 1) if recent else 0
        old_per_day = len(older) / max(older[-1]["date"]["days_ago"], 1) if older else 0
        if old_per_day > 0:
            trend_pct = round((rec_per_day - old_per_day) / old_per_day * 100)

    # First-seen and peak month
    months = Counter(
        r["date"]["iso"][:7] for r in matched_reviews
        if r["date"].get("iso")
    )
    peak_month = months.most_common(1)[0][0] if months else None
    first_seen = min(months.keys()) if months else None

    # Severity tier
    if avg_rating <= 2.0 and n >= 5:
        severity = "critical"
    elif avg_rating <= 3.0 or n >= 10:
        severity = "warning"
    else:
        severity = "notable"

    # Best exemplar = highest helpful_count
    best = max(matched_reviews, key=lambda r: r["engagement"]["helpful_count"])

    return {
        "id":             cid,
        "type":           ctype,
        "label":          label,
        "icon":           icon,
        "category":       category,
        "description":    description,
        "size":           n,
        "review_count":   n,
        "avg_rating":     round(avg_rating, 2),
        "severity":       severity,
        "trend_pct":      trend_pct,
        "trend_label":    "▲ growing"  if trend_pct >  20 else
                          "▼ declining" if trend_pct < -20 else
                          "▬ stable",
        "helpful_total":  helpful,
        "verified_pct":   round(verified / n * 100) if n else 0,
        "first_seen":     first_seen,
        "peak_month":     peak_month,
        "top_phrases":    sample_phrases[:3],
        "exemplar":       (best["comment"]["text"] or "")[:240],
        "exemplar_author": best["author"]["name"],
        "exemplar_rating": best["rating"],
        "exemplar_helpful": best["engagement"]["helpful_count"],
        "review_ids":     [r["id"] for r in matched_reviews[:30]],
    }


def cluster_complaints(reviews, k=5, taxonomy_aspects=None, aspects=None):
    """Smart complaint clustering with three layers:

      1. PATTERN clusters    — handcrafted regex archetypes (high precision)
      2. ASPECT clusters     — per-aspect negative concentration
      3. KMEANS residual     — catch-all for remaining negative reviews

    Returns clusters ranked by size, capped at the top 8.
    Each cluster ships rich stats: severity tier, MoM trend, top phrases,
    exemplar review with author + helpful count, verified %.
    """
    if not reviews:
        return []

    # Layer 1: pattern detection
    pattern_clusters, consumed = _detect_pattern_clusters(reviews)

    # Layer 2: aspect-anchored
    aspect_clusters = _detect_aspect_clusters(reviews, aspects or {},
                                              taxonomy_aspects, consumed)

    # Layer 3: KMeans on residual
    residual_clusters = _detect_kmeans_residual(reviews, consumed, k=3)

    all_clusters = pattern_clusters + aspect_clusters + residual_clusters
    all_clusters.sort(key=lambda c: (
        # Critical first, then warning, then notable
        {"critical": 0, "warning": 1, "notable": 2}.get(c["severity"], 3),
        -c["size"],
    ))
    return all_clusters[:8]


# ---------------------------------------------------------------------------
# Time-series & geo aggregates (now possible with fixed dates)
# ---------------------------------------------------------------------------

def build_timeseries(reviews: list[dict]) -> list[dict]:
    """Monthly buckets: count, avg rating, avg sentiment."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in reviews:
        iso = r["date"].get("iso")
        if not iso:
            continue
        key = iso[:7]
        buckets[key].append(r)

    out = []
    for month in sorted(buckets):
        rs = buckets[month]
        out.append({
            "month": month,
            "n": len(rs),
            "avg_rating":    round(sum(r["rating"] for r in rs) / len(rs), 2),
            "avg_sentiment": round(
                sum(r["analysis"]["sentiment_score"] for r in rs) / len(rs), 3
            ),
            "positive": sum(1 for r in rs if r["analysis"]["sentiment_label"] == "positive"),
            "negative": sum(1 for r in rs if r["analysis"]["sentiment_label"] == "negative"),
        })
    return out


def build_geo(reviews: list[dict]) -> dict[str, dict]:
    """State-level: count, avg rating, sentiment split."""
    by_state: dict[str, list[dict]] = defaultdict(list)
    for r in reviews:
        st = r["author"]["location"]["state"]
        if st:
            by_state[st].append(r)
    return {
        st: {
            "n": len(rs),
            "avg_rating": round(sum(r["rating"] for r in rs) / len(rs), 2),
            "positive":   sum(1 for r in rs if r["analysis"]["sentiment_label"] == "positive"),
            "negative":   sum(1 for r in rs if r["analysis"]["sentiment_label"] == "negative"),
        }
        for st, rs in by_state.items()
    }


# ───────────────────────────────────────────────────────────────────────────
# Phase 3 additions — design-driven analyses
# ───────────────────────────────────────────────────────────────────────────

LOGISTICS_TERMS = {
    "flipkart", "delivery", "deliver", "delivered", "shipping", "shipped",
    "package", "packaging", "open box", "open-box", "openbox", "return",
    "returned", "refund", "warranty", "courier", "seller", "exchange",
    "replacement", "service", "support",
}


def compute_certified_split(reviews):
    """Verified vs unverified rating + sentiment distribution."""
    n = len(reviews)
    if not n:
        return None
    ver = [r for r in reviews if r["author"]["verified"]]
    unv = [r for r in reviews if not r["author"]["verified"]]

    def stats(group):
        if not group:
            return {"rating": 0.0, "count": 0, "pct": 0, "dist": [0, 0, 0]}
        avg = sum(r["rating"] for r in group) / len(group)
        pos = sum(1 for r in group if r["analysis"]["sentiment_label"] == "positive")
        neu = sum(1 for r in group if r["analysis"]["sentiment_label"] == "neutral")
        neg = sum(1 for r in group if r["analysis"]["sentiment_label"] == "negative")
        return {"rating": round(avg, 2), "count": len(group),
                "pct": round(len(group) / n * 100), "dist": [pos, neu, neg]}

    return {"verified": stats(ver), "unverified": stats(unv)}


def detect_review_burst(reviews):
    """Find days with anomalous review counts (>5x median)."""
    by_day = defaultdict(int)
    for r in reviews:
        iso = r["date"].get("iso")
        if iso:
            by_day[iso] += 1
    if not by_day:
        return None
    counts = sorted(by_day.values())
    median = counts[len(counts) // 2] if counts else 1
    spikes = [(d, c) for d, c in by_day.items() if c >= max(median * 5, 5)]
    if spikes:
        d, c = max(spikes, key=lambda x: x[1])
        return {"date": d, "count": c}
    return None


def detect_duplicates(reviews):
    """Find phrases (4+ words) repeated across multiple reviews."""
    phrase_counts = Counter()
    for r in reviews:
        text = (r["comment"]["text"] or "").lower()
        words = re.findall(r"[a-z]+", text)
        for i in range(len(words) - 4):
            phrase = " ".join(words[i:i + 5])
            phrase_counts[phrase] += 1
    common = [(p, c) for p, c in phrase_counts.most_common(20) if c >= 3]
    return common[:5]


def compute_burst_chart(reviews, weeks=12):
    """Weekly review count histogram for the last N weeks."""
    weekly = defaultdict(int)
    today = datetime.now(timezone.utc).date()
    for r in reviews:
        if r["date"].get("days_ago") is None:
            continue
        d = r["date"]["days_ago"]
        if 0 <= d <= weeks * 7:
            week_idx = weeks - 1 - (d // 7)
            if 0 <= week_idx < weeks:
                weekly[week_idx] += 1
    if not weekly:
        return [30] * weeks
    max_v = max(weekly.values()) or 1
    return [round(weekly.get(i, 0) / max_v * 100) for i in range(weeks)]


def compute_forensics(reviews):
    """Trust score components + signal list."""
    n = len(reviews) or 1
    verified_count = sum(1 for r in reviews if r["author"]["verified"])
    cert_pct = verified_count / n * 100

    word_counts = sorted(r["comment"]["word_count"] for r in reviews)
    median_words = word_counts[len(word_counts) // 2] if word_counts else 0

    burst = detect_review_burst(reviews)
    dupes = detect_duplicates(reviews)
    burst_chart = compute_burst_chart(reviews, 12)

    score = 6.0
    if cert_pct >= 80:
        score += 1.5
    elif cert_pct >= 50:
        score += 0.7
    if median_words >= 30:
        score += 0.8
    elif median_words >= 15:
        score += 0.4
    if not burst:
        score += 0.6
    else:
        score -= 0.4
    if not dupes:
        score += 0.5
    else:
        score -= 0.3 * min(len(dupes), 3)
    score = max(1.0, min(10.0, score))

    signals = [
        {
            "status": "ok" if cert_pct >= 70 else "warn",
            "name":   "Certified-buyer ratio",
            "sub":    f"{round(cert_pct)}% of reviews are verified purchases",
            "val":    f"{round(cert_pct)}%",
        },
        {
            "status": "ok" if median_words >= 20 else "warn",
            "name":   "Review depth",
            "sub":    f"Median {median_words} words per review",
            "val":    "Strong" if median_words >= 30 else "Thin",
        },
    ]
    if burst:
        signals.append({
            "status": "warn",
            "name":   f"Review burst on {burst['date']}",
            "sub":    f"{burst['count']} reviews in a single day",
            "val":    "Flagged",
        })
    else:
        signals.append({
            "status": "ok",
            "name":   "Review timing pattern",
            "sub":    "No suspicious volume spikes detected",
            "val":    "Normal",
        })
    if dupes:
        top = dupes[0]
        signals.append({
            "status": "warn",
            "name":   "Duplicate phrasing",
            "sub":    f'"{top[0][:50]}…" — {top[1]}×',
            "val":    f"{len(dupes)} dupes",
        })
    else:
        signals.append({
            "status": "ok",
            "name":   "Phrase diversity",
            "sub":    "No suspicious phrase repetition",
            "val":    "Healthy",
        })

    risk = "Low fake-review risk" if score >= 7 else \
           "Some red flags"        if score >= 5 else \
           "High fake-review risk"

    return {
        "score":   round(score, 1),
        "risk":    risk,
        "signals": signals,
        "burst_chart": burst_chart,
    }


def compute_logistics_split(reviews, aspects):
    """Split reviews into product-focused vs logistics-focused; compute net per group."""
    n = len(reviews)
    log_reviews = [r for r in reviews
                   if any(t in (r["comment"]["text"] or "").lower() for t in LOGISTICS_TERMS)]
    prod_reviews = [r for r in reviews if r not in log_reviews]

    def stats(group):
        if not group:
            return {"net": 0, "pos": 0, "neu": 0, "neg": 0, "count": 0, "pct": 0}
        pos = sum(1 for r in group if r["analysis"]["sentiment_label"] == "positive")
        neg = sum(1 for r in group if r["analysis"]["sentiment_label"] == "negative")
        neu = sum(1 for r in group if r["analysis"]["sentiment_label"] == "neutral")
        net = round((pos - neg) / len(group) * 100)
        return {"net": net, "pos": pos, "neu": neu, "neg": neg,
                "count": len(group), "pct": round(len(group) / n * 100) if n else 0}

    prod = stats(prod_reviews)
    top_aspects = sorted(
        [(ASPECT_LABEL_MAP.get(k, k), int(round((a["pos"] - a["neg"]) / max(a["sentences"], 1) * 100)))
         for k, a in aspects.items() if a["mentions"] > 0],
        key=lambda x: -abs(x[1]),
    )[:4]
    prod["aspects"] = top_aspects
    return {"product": prod, "logistics": stats(log_reviews)}


ASPECT_LABEL_MAP = {
    "sound": "Sound quality", "battery": "Battery life", "anc": "Active noise cancel",
    "mic": "Mic / call quality", "comfort": "Comfort & fit", "build": "Build quality",
    "controls": "Touch controls", "connectivity": "App & connectivity", "value": "Value for money",
}


def compute_longevity(reviews):
    """Bucket reviews by tenure (days since posting) and compute avg rating per bucket."""
    buckets = {
        "Day 1":    [],   # 0-7 days
        "1 month":  [],   # 8-45
        "6 months": [],   # 46-200
        "1 year":   [],   # 201-450
        "2 years+": [],   # 450+
    }
    for r in reviews:
        d = r["date"].get("days_ago")
        if d is None:
            continue
        rating = r["rating"]
        if d <= 7:        buckets["Day 1"].append(rating)
        elif d <= 45:     buckets["1 month"].append(rating)
        elif d <= 200:    buckets["6 months"].append(rating)
        elif d <= 450:    buckets["1 year"].append(rating)
        else:             buckets["2 years+"].append(rating)

    points = []
    last_rating = None
    for label, ratings in buckets.items():
        if not ratings:
            continue
        avg = sum(ratings) / len(ratings)
        delta = ""
        delta_ok = False
        if last_rating is not None:
            diff = avg - last_rating
            if abs(diff) > 0.1:
                delta = f"{'↑' if diff > 0 else '↓'} {abs(diff):.1f}★"
                delta_ok = diff > 0
            else:
                delta = "≈ steady"
        else:
            delta = "↑ baseline"
            delta_ok = True
        points.append({
            "label":   label,
            "rating":  round(avg, 2),
            "n":       len(ratings),
            "delta":   delta,
            "delta_ok": delta_ok,
        })
        last_rating = avg

    return {
        "points":            points,
        "top_failure":       "Battery / Quality" if any(p["rating"] < 3 for p in points) else None,
        "top_failure_pct":   "from negative cluster mix" if any(p["rating"] < 3 for p in points) else "",
    }


def compute_verdict(aspects, aggregates):
    """Worth buying / Mixed / Skip + supporting points + confidence."""
    avg = aggregates["average_rating"]
    n = aggregates["total_reviews"]
    pos_pct = (aggregates["sentiment_distribution"].get("positive", 0) / n) if n else 0
    neg_pct = (aggregates["sentiment_distribution"].get("negative", 0) / n) if n else 0

    if avg >= 4.0 and pos_pct > 0.55:
        decision = "Worth buying"
    elif avg >= 3.0:
        decision = "Mixed"
    else:
        decision = "Skip"

    ranked = sorted(
        [(k, a) for k, a in aspects.items() if a["mentions"] > 0],
        key=lambda x: -(x[1]["pos"] - x[1]["neg"]),
    )
    pros = ranked[:2]
    cons = ranked[-2:][::-1] if len(ranked) >= 4 else []

    points = []
    for k, a in pros:
        points.append({"ok": True, "text": f"Strong {ASPECT_LABEL_MAP.get(k, k).lower()}"})
    for k, a in cons:
        if (a["neg"] - a["pos"]) > 0:
            points.append({"ok": False, "text": f"Weak {ASPECT_LABEL_MAP.get(k, k).lower()}"})

    if not points:
        points.append({"ok": True, "text": "Adequate sample size"})

    confidence = min(95, max(40, round(40 + n / 6 + pos_pct * 30 - neg_pct * 20)))

    cond = ""
    if decision == "Worth buying" and cons:
        cond = f"If {ASPECT_LABEL_MAP.get(cons[0][0], cons[0][0]).lower()} isn't your top priority"
    elif decision == "Mixed":
        cond = "Mixed reviews — read carefully"

    return {"decision": decision, "condition": cond, "confidence": confidence, "points": points}


def compute_one_star_complaints(reviews, clusters):
    """Top 3 complaint themes among 1-star reviews."""
    one_star = [r for r in reviews if r["rating"] == 1]
    if not one_star:
        return []
    one_star_ids = {r["id"] for r in one_star}
    matches = []
    for c in clusters:
        in_one = sum(1 for rid in c["review_ids"] if rid in one_star_ids)
        if in_one >= 2:
            label = (c.get("label") or "").split("/")[0].strip().capitalize() or "Issue"
            matches.append({"label": label, "count": in_one})
    matches.sort(key=lambda x: -x["count"])
    total = sum(m["count"] for m in matches[:5]) or 1
    return [{"label": m["label"], "pct": round(m["count"] / total * 100)} for m in matches[:3]]


def compute_who_should_buy(aspects, aggregates):
    """Heuristic 'who should buy' paragraph + tag list."""
    ranked = sorted(
        [(k, a) for k, a in aspects.items() if a["mentions"] > 0],
        key=lambda x: -(x[1]["pos"] - x[1]["neg"]),
    )
    if not ranked:
        return {"paragraph": "Not enough aspect data to generate a buying recommendation.",
                "for_tags": [], "against_tags": []}

    top = [k for k, _ in ranked[:2]]
    bot = [k for k, a in ranked if (a["neg"] - a["pos"]) > 0][-2:]

    pos_phrases = " and ".join(ASPECT_LABEL_MAP.get(k, k).lower() for k in top)
    neg_phrases = " or ".join(ASPECT_LABEL_MAP.get(k, k).lower() for k in bot) if bot else None

    paragraph = (
        f"Buyers who prioritize {pos_phrases} will find this product strong. "
        + (f"Skip if your primary concern is {neg_phrases}." if neg_phrases else "")
    )

    use_case_tags = {
        "sound":        "Music-first",
        "battery":      "All-day use",
        "anc":          "Travel / commute",
        "mic":          "Voice calls",
        "comfort":      "Long sessions",
        "build":        "Daily abuse",
        "value":        "Budget-conscious",
        "connectivity": "Multi-device",
        "controls":     "Quick controls",
    }
    for_tags = [use_case_tags[k] for k in top if k in use_case_tags]
    against_tags = [use_case_tags[k] for k in bot if k in use_case_tags]
    return {"paragraph": paragraph, "for_tags": for_tags, "against_tags": against_tags}


# ───────────────────────────────────────────────────────────────────────────
# Variant breakdown + photo gallery (from scraper-extracted attrs/images)
# ───────────────────────────────────────────────────────────────────────────

import json as _json


def compute_variants(reviews: list[dict]) -> list[dict]:
    """Group reviews by their dominant product attribute (color, size, etc.)
    and compute sentiment + rating per variant."""
    if not reviews:
        return []

    # Pick the single attribute name that occurs most frequently
    attr_counts: Counter = Counter()
    parsed_attrs = []
    for r in reviews:
        raw = r.get("attrs") or "{}"
        try:
            attrs = _json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            attrs = {}
        parsed_attrs.append(attrs)
        for k in attrs:
            attr_counts[k] += 1
    if not attr_counts:
        return []
    primary = attr_counts.most_common(1)[0][0]

    # Group reviews by primary attr value
    by_variant: dict[str, list[dict]] = defaultdict(list)
    for r, attrs in zip(reviews, parsed_attrs):
        val = attrs.get(primary)
        if not val or len(val) > 40:
            continue
        by_variant[val.strip()].append(r)

    if len(by_variant) < 2:
        return []

    variants = []
    for value, rs in by_variant.items():
        if len(rs) < 2:
            continue
        avg = sum(r["rating"] for r in rs) / len(rs)
        pos = sum(1 for r in rs if r["analysis"]["sentiment_label"] == "positive")
        neu = sum(1 for r in rs if r["analysis"]["sentiment_label"] == "neutral")
        neg = sum(1 for r in rs if r["analysis"]["sentiment_label"] == "negative")
        variants.append({
            "attribute": primary.title(),
            "value":     value,
            "count":     len(rs),
            "avg_rating": round(avg, 2),
            "pos": pos, "neu": neu, "neg": neg,
            "review_ids": [r["id"] for r in rs[:30]],
        })
    if not variants:
        return []

    variants.sort(key=lambda v: -v["avg_rating"])
    if variants:
        variants[0]["tag"] = "Best rated"
    if len(variants) > 1:
        variants[-1]["tag"] = "Lowest rated"
    # Bestseller = highest count
    bestseller = max(variants, key=lambda v: v["count"])
    if "tag" not in bestseller:
        bestseller["tag"] = "Bestseller"
    return variants


def compute_photos(reviews: list[dict], max_thumbs: int = 12) -> dict:
    """Collect review-attached photos with a heuristic cluster label per image."""
    photos = []
    cluster_counts: Counter = Counter()
    for r in reviews:
        raw = r.get("images") or "[]"
        try:
            urls = _json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception:
            urls = []
        if not urls:
            continue
        text = (r["comment"]["text"] or "").lower()
        # Cluster heuristic
        if any(w in text for w in ["broke", "damage", "damaged", "defect", "scratch", "torn", "crack"]):
            cluster = "damaged"
        elif any(w in text for w in ["unbox", "package", "delivery", "received"]):
            cluster = "unboxing"
        elif any(w in text for w in ["wearing", "fit", "on me", "in use", "using"]):
            cluster = "in-use"
        elif any(w in text for w in ["compare", "vs", "size"]):
            cluster = "compare"
        else:
            cluster = "general"
        cluster_counts[cluster] += len(urls)
        for u in urls:
            photos.append({
                "url":        u,
                "cluster":    cluster,
                "review_id":  r["id"],
                "rating":     r["rating"],
            })

    return {
        "total":    len(photos),
        "thumbs":   photos[:max_thumbs],
        "clusters": dict(cluster_counts.most_common(6)),
    }


# ───────────────────────────────────────────────────────────────────────────
# Product-spec / review alignment
# ───────────────────────────────────────────────────────────────────────────

# Map common spec keys to our aspect keys, so we can correlate.
SPEC_TO_ASPECT_HINTS = {
    "noise cancellation":         "anc",
    "active noise cancellation":  "anc",
    "anc":                        "anc",
    "battery":                    "battery",
    "battery capacity":           "battery",
    "battery backup":             "battery",
    "playback time":              "battery",
    "fast charging":              "battery",
    "charging":                   "battery",
    "microphone":                 "mic",
    "mic":                        "mic",
    "with microphone":            "mic",
    "deep bass":                  "sound",
    "sound":                      "sound",
    "audio":                      "sound",
    "driver type":                "sound",
    "driver size":                "sound",
    "stereo":                     "sound",
    "connectivity":               "connectivity",
    "bluetooth":                  "connectivity",
    "bluetooth version":          "connectivity",
    "wireless":                   "connectivity",
    "headphone type":             "build",
    "headphone design":           "build",
    "build":                      "build",
    "design":                     "build",
    "color":                      "build",
    "brand color":                "build",
    "weight":                     "build",
    "controls":                   "controls",
    "touch":                      "controls",
    "inline remote":              "controls",
    "comfort":                    "comfort",
    "fit":                        "comfort",
    "ear-tip":                    "comfort",
    # phone-specific
    "display":                    "display",
    "display size":               "display",
    "display type":               "display",
    "resolution":                 "display",
    "refresh rate":               "display",
    "camera":                     "camera",
    "primary camera":             "camera",
    "front camera":               "camera",
    "rear camera":                "camera",
    "ram":                        "performance",
    "processor":                  "performance",
    "operating system":           "software",
    "os":                         "software",
    "internal storage":           "performance",
    "speaker":                    "speaker",
    # tv
    "smart tv":                   "smart",
    # generic Flipkart fields (caught for any product)
    "warranty":                   "value",
    "warranty summary":           "value",
    "model id":                   "build",
    "model":                      "build",
    "model number":               "build",
    "model name":                 "build",
    "brand color":                "design",
    "color":                      "design",
    "colour":                     "design",
    "weight":                     "build",
    "material":                   "build",
    "body material":              "build",
    "sales package":              "quality",
    "in the box":                 "quality",
    "country of origin":          "quality",
    "manufacturer":               "quality",
    "ergonomics":                 "comfort",
    "console":                    "performance",
    "frame rate":                 "performance",
    "compatible devices":         "connectivity",
    "ports":                      "connectivity",
    "capacity":                   "capacity",
    "size":                       "size",
    "dimensions":                 "size",
    "input voltage":              "performance",
    "power":                      "performance",
    "wattage":                    "performance",
    "primary use":                "ease",
    "primary purpose":            "ease",
    "type":                       "build",
    "ssd":                        "performance",
    "graphics":                   "performance",
}


def align_specs_with_aspects(product: dict, aspects: dict) -> list[dict]:
    """Pair product spec claims with review-mined sentiment to reveal
    spec-vs-reality alignment. Returns ranked rows."""
    if not product or not product.get("specs"):
        return []
    rows = []
    seen = set()
    flat_specs: list[tuple[str, str]] = []
    for grp in product["specs"].values():
        for k, v in grp.items():
            flat_specs.append((k, v))

    for spec_key, spec_val in flat_specs:
        norm = spec_key.lower().strip()
        aspect_key = SPEC_TO_ASPECT_HINTS.get(norm)
        if not aspect_key:
            for hint, ak in SPEC_TO_ASPECT_HINTS.items():
                if hint in norm:
                    aspect_key = ak
                    break
        if not aspect_key or aspect_key not in aspects:
            continue
        if aspect_key in seen:
            continue
        seen.add(aspect_key)

        a = aspects[aspect_key]
        if a["mentions"] == 0:
            continue

        net = round((a["pos"] - a["neg"]) / max(a["sentences"], 1) * 100)
        if net >= 50:
            verdict, tone = "Lives up to spec", "ok"
        elif net >= 0:
            verdict, tone = "Mixed reception", "warn"
        else:
            verdict, tone = "Underperforms claim", "bad"

        rows.append({
            "spec_key":     spec_key,
            "spec_value":   spec_val,
            "aspect_key":   aspect_key,
            "aspect_label": ASPECT_LABEL_MAP.get(aspect_key, aspect_key.title()),
            "rating":       a["rating"],
            "mentions":     a["mentions"],
            "net":          net,
            "pos":          a["pos"],
            "neg":          a["neg"],
            "verdict":      verdict,
            "tone":         tone,
        })

    rows.sort(key=lambda r: -r["mentions"])
    return rows[:12]


def find_reviewer_surprises(product, aspects, taxonomy_aspects=None):
    """Aspects buyers discuss heavily that the listing's spec sheet doesn't
    mention. Surfaces hidden upsides (✓) and hidden flaws (✗).

    Logic: collect every aspect that maps to ANY spec key (those are
    'advertised'). Any other aspect with ≥5 mentions and meaningful net
    sentiment is a 'reviewer surprise'.
    """
    if not aspects:
        return []

    advertised = set()
    if product and product.get("specs"):
        for grp in product["specs"].values():
            for k in grp:
                norm = k.lower().strip()
                ak = SPEC_TO_ASPECT_HINTS.get(norm)
                if not ak:
                    for hint, hint_ak in SPEC_TO_ASPECT_HINTS.items():
                        if hint in norm:
                            ak = hint_ak
                            break
                if ak:
                    advertised.add(ak)

    out = []
    for aspect_key, agg in aspects.items():
        if aspect_key in advertised:
            continue
        if agg["mentions"] < 5:
            continue
        sentences = agg.get("sentences", 0) or 1
        net = round((agg["pos"] - agg["neg"]) / sentences * 100)
        if abs(net) < 15 and agg["mentions"] < 10:
            continue
        meta = (taxonomy_aspects or {}).get(aspect_key, {})
        out.append({
            "aspect_key":   aspect_key,
            "aspect_label": meta.get("label", aspect_key.title()),
            "icon":         meta.get("icon", "spark"),
            "mentions":     agg["mentions"],
            "net":          net,
            "rating":       agg.get("rating"),
            "tone":         "pos" if net >= 25 else "neg" if net <= -25 else "neu",
            "kind":         "Hidden upside" if net >= 25 else "Hidden flaw" if net <= -25 else "Mixed",
        })

    # Rank by impact = |net| × ln(mentions)
    import math
    out.sort(key=lambda x: -abs(x["net"]) * math.log(x["mentions"] + 1), reverse=False)
    out.sort(key=lambda x: -(abs(x["net"]) * math.log(x["mentions"] + 1)))
    return out[:8]


# ───────────────────────────────────────────────────────────────────────────
# Use-case clustering ("What buyers actually use it for")
# ───────────────────────────────────────────────────────────────────────────

def compute_use_cases(reviews, taxonomy_use_cases):
    """For each use-case in the taxonomy, find reviews that mention its
    keywords and compute net sentiment + sample phrases.

    Returns a list of dicts ready for the frontend, sorted by mention count.
    """
    if not reviews or not taxonomy_use_cases:
        return []

    out = []
    for uc in taxonomy_use_cases:
        matched_ids = set()
        sample_phrases: list[str] = []
        pos = neu = neg = 0
        for r in reviews:
            text = (r["comment"]["text"] or "").lower()
            for kw in uc["keywords"]:
                if kw in text:
                    matched_ids.add(r["id"])
                    label = r["analysis"]["sentiment_label"]
                    if label == "positive": pos += 1
                    elif label == "negative": neg += 1
                    else: neu += 1
                    if len(sample_phrases) < 3:
                        idx = text.find(kw)
                        snippet = text[max(0, idx - 22): min(len(text), idx + 28)].strip()
                        snippet = re.sub(r"\s+", " ", snippet)
                        if snippet and snippet not in sample_phrases:
                            sample_phrases.append(snippet)
                    break
        if not matched_ids:
            continue
        n = len(matched_ids)
        net = round((pos - neg) / n * 100)
        out.append({
            "label":          uc["label"],
            "icon":           uc.get("icon", "spark"),
            "mentions":       n,
            "net":            net,
            "pos":            pos,
            "neu":            neu,
            "neg":            neg,
            "sample_phrases": sample_phrases,
            "review_ids":     list(matched_ids)[:30],
        })

    out.sort(key=lambda x: -x["mentions"])
    return out


# ───────────────────────────────────────────────────────────────────────────
# Reviewer profile ("Who's reviewing this")
# ───────────────────────────────────────────────────────────────────────────

def compute_reviewer_profile(reviews, city_tier_fn):
    """Compute reviewer demographics + authenticity-signal proxies.

    `city_tier_fn` is the per-module city→tier classifier (passed in from
    the caller so this function stays decoupled from the taxonomy module).
    """
    n = len(reviews) or 1

    # By city tier
    tier_counts = Counter()
    city_counts = Counter()
    for r in reviews:
        city = (r["author"]["location"] or {}).get("city")
        tier = city_tier_fn(city)
        if tier:
            tier_counts[tier] += 1
        if city:
            city_counts[city] += 1

    placed = sum(tier_counts.values()) or 1
    by_tier = {
        "tier1": tier_counts.get("tier1", 0),
        "tier2": tier_counts.get("tier2", 0),
        "tier3": tier_counts.get("tier3", 0),
        "placed":   placed,
        "tier1_pct": round(tier_counts.get("tier1", 0) / placed * 100),
        "tier2_pct": round(tier_counts.get("tier2", 0) / placed * 100),
        "tier3_pct": round(tier_counts.get("tier3", 0) / placed * 100),
    }
    top_cities = [{"name": c, "count": cnt} for c, cnt in city_counts.most_common(5)]

    # Reviewer profile metrics (proxies built from what we DO have)
    long_reviews   = sum(1 for r in reviews if r["comment"]["word_count"] >= 50)
    has_photo_text = sum(1 for r in reviews
                         if r.get("images") and r["images"] not in ("", "[]", "null"))
    helpful_top    = sum(1 for r in reviews if r["engagement"]["helpful_count"] >= 3)
    verified_count = sum(1 for r in reviews if r["author"]["verified"])
    multiline      = sum(1 for r in reviews if r["comment"]["is_multiline"])

    # Median review tenure (days_ago) — proxy for "median acct age"
    days_list = [r["date"]["days_ago"] for r in reviews if r["date"].get("days_ago")]
    days_list.sort()
    median_days = days_list[len(days_list) // 2] if days_list else 0
    if median_days >= 365:
        tenure_str = f"{round(median_days / 365, 1)}y"
        tenure_label = "Median review age"
    elif median_days >= 30:
        tenure_str = f"{round(median_days / 30)}mo"
        tenure_label = "Median review age"
    else:
        tenure_str = f"{median_days}d"
        tenure_label = "Median review age"

    return {
        "by_tier":      by_tier,
        "top_cities":   top_cities,
        "metrics": [
            {
                "value":       f"{round(verified_count / n * 100)}%",
                "label":       "Verified buyers",
                "sub":         "Confirmed Flipkart purchases",
                "tone":        "ok" if verified_count / n >= 0.9 else "warn",
            },
            {
                "value":       tenure_str,
                "label":       tenure_label,
                "sub":         "Review tenure across this product",
                "tone":        "neutral",
            },
            {
                "value":       f"{round(long_reviews / n * 100)}%",
                "label":       "Wrote 50+ words",
                "sub":         "Detailed reviews — not generic",
                "tone":        "ok" if long_reviews / n >= 0.3 else "warn",
            },
            {
                "value":       f"{round(has_photo_text / n * 100)}%" if has_photo_text else "—",
                "label":       "Added photos" if has_photo_text else "No photo signal",
                "sub":         "Visual proof of purchase" if has_photo_text else "Flipkart didn't return media URLs",
                "tone":        "ok" if has_photo_text / n >= 0.1 else "neutral",
            },
            {
                "value":       f"{round(helpful_top / n * 100)}%",
                "label":       "≥3 helpful votes",
                "sub":         "Reviews other buyers found useful",
                "tone":        "ok" if helpful_top / n >= 0.15 else "neutral",
            },
            {
                "value":       f"{round(multiline / n * 100)}%",
                "label":       "Structured reviews",
                "sub":         "Multi-line, broken into points",
                "tone":        "ok" if multiline / n >= 0.15 else "neutral",
            },
        ],
        "total_reviews":  n,
    }
