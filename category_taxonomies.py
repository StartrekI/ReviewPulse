"""
Per-category aspect taxonomies for ReviewPulse.

Each category lists the aspects users actually discuss for products in that
category, with keyword triggers, a label, and an SVG-icon name. Detection
runs on the product URL slug + an optional sample of review text.

Add a new category by extending CATEGORIES; the analysis pipeline will pick
it up automatically.
"""

from __future__ import annotations

import re

# -----------------------------------------------------------------------------
# Reusable icon paths (16x16 viewBox, 1.4 stroke)
# -----------------------------------------------------------------------------
ICONS = {
    "speaker":    '<path d="M8 3 5 6H2v4h3l3 3V3Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M11 6c.7.7 1 1.4 1 2s-.3 1.3-1 2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
    "battery":    '<rect x="2" y="5" width="11" height="6" rx="1.5" stroke="currentColor" stroke-width="1.4"/><rect x="13.5" y="6.5" width="1.5" height="3" rx=".5" fill="currentColor"/><rect x="3.5" y="6.5" width="3" height="3" rx=".5" fill="currentColor"/>',
    "headphones": '<path d="M8 2a6 6 0 0 0-6 6v2h2v-2a4 4 0 0 1 8 0v2h2V8a6 6 0 0 0-6-6Z" stroke="currentColor" stroke-width="1.4"/><rect x="2" y="9" width="3" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="11" y="9" width="3" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/>',
    "mic":        '<rect x="6" y="2" width="4" height="8" rx="2" stroke="currentColor" stroke-width="1.4"/><path d="M3 8a5 5 0 0 0 10 0M8 13v2M5.5 15h5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
    "diamond":    '<path d="m2 6 6-3 6 3-6 3-6-3Zm0 4 6 3 6-3" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
    "phone":      '<rect x="3" y="2" width="10" height="12" rx="2" stroke="currentColor" stroke-width="1.4"/><path d="M7 11h2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
    "tap":        '<circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.4"/>',
    "rupee":      '<path d="M4 3h8M4 6h8M5 3c3 0 4 3 0 4M5 7l5 6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
    "camera":     '<rect x="2" y="5" width="12" height="9" rx="1.5" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="9.5" r="2.5" stroke="currentColor" stroke-width="1.4"/><path d="M5 5l1-2h4l1 2" stroke="currentColor" stroke-width="1.4"/>',
    "monitor":    '<rect x="2" y="3" width="12" height="8" rx="1.5" stroke="currentColor" stroke-width="1.4"/><path d="M5 14h6M8 11v3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
    "cpu":        '<rect x="3" y="3" width="10" height="10" rx="1.5" stroke="currentColor" stroke-width="1.4"/><rect x="6" y="6" width="4" height="4" stroke="currentColor" stroke-width="1.4"/>',
    "bed":        '<path d="M2 10v3M14 10v3M2 10h12M3 10V8a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
    "ruler":      '<path d="M3 8h10v3H3zM5 8v2M7 8v3M9 8v2M11 8v3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
    "clock":      '<circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.4"/><path d="M8 5v3l2 1" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
    "tv":         '<rect x="2" y="3" width="12" height="9" rx="1.5" stroke="currentColor" stroke-width="1.4"/><path d="M5 14h6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
    "pot":        '<path d="M3 7h10v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" stroke="currentColor" stroke-width="1.4"/><path d="M5 7V5a3 3 0 0 1 6 0v2M2 7h12" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
    "shoe":       '<path d="M2 11c1-3 3-3 5-3l3 1c1 0 1 1 1 2l1 1h1v2H2v-3Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
    "shirt":      '<path d="M3 5l3-2 2 1 2-1 3 2-1 3h-1v6H4V8H3l1-3Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
    "bag":        '<path d="M3 5h10l1 9H2l1-9Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M5 5V4a3 3 0 0 1 6 0v1" stroke="currentColor" stroke-width="1.4"/>',
    "drop":       '<path d="M8 2l4 6c1 2 0 5-2 6s-5 1-6-1-1-3 0-5l4-6Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
    "spark":      '<path d="M8 2v4M8 10v4M2 8h4M10 8h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
    "shield":     '<path d="M8 2 14 4v4c0 3-2 5-6 7-4-2-6-4-6-7V4l6-2Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
    "wifi":       '<path d="M2 6.5C4 5 6 4 8 4s4 1 6 2.5M4 9c1-1 2.5-2 4-2s3 1 4 2M6.5 11.5c.5-.5 1-.7 1.5-.7s1 .2 1.5.7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><circle cx="8" cy="13.5" r="1" fill="currentColor"/>',
    "scale":      '<path d="M2 13h12M5 13l1-7h4l1 7M6 4h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
}


# -----------------------------------------------------------------------------
# Aspect taxonomy per category
#  Each aspect: {label, icon, keywords}
# -----------------------------------------------------------------------------

CATEGORIES: dict[str, dict] = {

    "earbuds": {
        "label": "Wireless audio (earbuds / headphones)",
        "url_keywords": ["buds", "earbud", "earphone", "headphone", "headset", "tws", "airdopes", "airpods", "neckband"],
        "title_keywords": ["earbud", "headphone", "earphone", "tws", "anc", "wireless audio"],
        "aspects": {
            "sound":        {"label": "Sound quality",      "icon": "speaker",    "keywords": ["sound","audio","music","bass","treble","clarity","loudness","volume","stereo","muddy","crisp"]},
            "anc":          {"label": "Active noise cancel","icon": "headphones", "keywords": ["anc","noise cancel","noise cancellation","active noise","ambient"]},
            "battery":      {"label": "Battery life",       "icon": "battery",    "keywords": ["battery","charge","charging","playback","backup","drain"]},
            "mic":          {"label": "Mic / call quality", "icon": "mic",        "keywords": ["mic","microphone","call quality","calls","voice"]},
            "comfort":      {"label": "Comfort & fit",      "icon": "diamond",    "keywords": ["comfort","fit","ear tip","ear-tip","headache","pressure","uncomfortable","snug","slipping"]},
            "connectivity": {"label": "Connectivity",       "icon": "wifi",       "keywords": ["bluetooth","connect","pairing","multipoint","switching","lag","latency","dropout"]},
            "build":        {"label": "Build quality",      "icon": "shield",     "keywords": ["build","design","case","material","durable","sturdy","cheap feel"]},
            "controls":     {"label": "Touch controls",     "icon": "tap",        "keywords": ["touch","tap","gesture","swipe","control","volume control"]},
            "value":        {"label": "Value for money",    "icon": "rupee",      "keywords": ["price","value","money","worth","cost","expensive","cheap","budget","vfm"]},
        },
    },

    "smartphone": {
        "label": "Smartphone",
        "url_keywords": ["smartphone","mobile","-phone","phone-","-5g-"],
        "title_keywords": ["smartphone","mobile phone","android phone","iphone"],
        "aspects": {
            "display":     {"label": "Display",        "icon": "monitor", "keywords": ["display","screen","amoled","oled","brightness","colour","color","resolution","refresh rate","hdr"]},
            "battery":     {"label": "Battery",        "icon": "battery", "keywords": ["battery","charging","fast charge","backup","drain","mah","screen on time","sot"]},
            "camera":      {"label": "Camera",         "icon": "camera",  "keywords": ["camera","photo","picture","video","selfie","night mode","portrait","zoom","megapixel"]},
            "performance": {"label": "Performance",    "icon": "cpu",     "keywords": ["performance","gaming","games","speed","lag","fast","slow","heating","heat","snapdragon","mediatek","processor","ram"]},
            "build":       {"label": "Build & design", "icon": "shield",  "keywords": ["build","design","look","feel","premium","plastic","metal","glass","weight","slim","thick"]},
            "software":    {"label": "Software",       "icon": "phone",   "keywords": ["software","ui","update","bloatware","ads","android","ios","stock","custom","oxygen","miui","funtouch"]},
            "speaker":     {"label": "Audio / speaker","icon": "speaker", "keywords": ["speaker","sound","loudness","stereo","headphone jack","audio"]},
            "network":     {"label": "Network / 5G",   "icon": "wifi",    "keywords": ["5g","4g","network","signal","wifi","reception","calls","connectivity"]},
            "value":       {"label": "Value",          "icon": "rupee",   "keywords": ["price","value","worth","money","cost","budget","vfm"]},
        },
    },

    "laptop": {
        "label": "Laptop",
        "url_keywords": ["laptop","notebook","macbook","chromebook"],
        "title_keywords": ["laptop","notebook","macbook"],
        "aspects": {
            "display":     {"label": "Display",        "icon": "monitor", "keywords": ["display","screen","brightness","colour","color","resolution","ips","oled","ppi"]},
            "battery":     {"label": "Battery life",   "icon": "battery", "keywords": ["battery","backup","hours","charging","power"]},
            "performance": {"label": "Performance",    "icon": "cpu",     "keywords": ["performance","speed","ram","ssd","intel","amd","ryzen","i5","i7","gaming","render","fast","slow"]},
            "keyboard":    {"label": "Keyboard",       "icon": "tap",     "keywords": ["keyboard","typing","keys","backlit","trackpad","touchpad"]},
            "build":       {"label": "Build & weight", "icon": "shield",  "keywords": ["build","design","weight","portable","slim","thick","heavy","light","material","aluminium"]},
            "thermals":    {"label": "Thermals",       "icon": "spark",   "keywords": ["heat","heating","thermal","fan","noise","loud"]},
            "ports":       {"label": "Ports",          "icon": "phone",   "keywords": ["port","usb","hdmi","jack","sd","thunderbolt","type c"]},
            "value":       {"label": "Value",          "icon": "rupee",   "keywords": ["price","value","worth","money","cost","budget"]},
        },
    },

    "smartwatch": {
        "label": "Smartwatch / wearable",
        "url_keywords": ["smartwatch","watch","-watch-","fitness-band","band-"],
        "title_keywords": ["smartwatch","watch","fitness band","fitness tracker"],
        "aspects": {
            "display":     {"label": "Display",         "icon": "monitor", "keywords": ["display","screen","amoled","brightness","always on","aod","colour"]},
            "battery":     {"label": "Battery life",    "icon": "battery", "keywords": ["battery","backup","days","charging","drain"]},
            "fitness":     {"label": "Fitness tracking","icon": "spark",   "keywords": ["fitness","workout","steps","heart rate","spo2","sleep","tracking","gps","calorie"]},
            "build":       {"label": "Build & comfort", "icon": "shield",  "keywords": ["build","strap","design","comfort","weight","wear","skin"]},
            "app":         {"label": "Companion app",   "icon": "phone",   "keywords": ["app","sync","pairing","bluetooth","connect","notification"]},
            "calls":       {"label": "Calls / mic",     "icon": "mic",     "keywords": ["call","mic","voice","speaker"]},
            "accuracy":    {"label": "Accuracy",        "icon": "tap",     "keywords": ["accuracy","accurate","wrong","off","incorrect","precise"]},
            "value":       {"label": "Value",           "icon": "rupee",   "keywords": ["price","value","worth","money","cost","budget"]},
        },
    },

    "tv": {
        "label": "Television",
        "url_keywords": ["tv","-led-","oled","qled","-uhd-","-4k-","smart-tv","-hd-tv-","tizen","webos"],
        "title_keywords": ["tv","television","smart tv","led tv"],
        "aspects": {
            "picture":     {"label": "Picture quality", "icon": "monitor", "keywords": ["picture","display","screen","colour","color","brightness","contrast","hdr","4k","resolution","sharp"]},
            "sound":       {"label": "Sound",           "icon": "speaker", "keywords": ["sound","audio","speaker","bass","loud","clear","dolby"]},
            "smart":       {"label": "Smart features", "icon": "wifi",     "keywords": ["smart","app","netflix","prime","youtube","wifi","internet","os","tizen","webos","google tv"]},
            "remote":      {"label": "Remote",          "icon": "tap",     "keywords": ["remote","button","voice command","quick"]},
            "build":       {"label": "Build & design",  "icon": "shield",  "keywords": ["build","design","slim","bezel","stand","wall mount","look"]},
            "ports":       {"label": "Connectivity",    "icon": "phone",   "keywords": ["hdmi","usb","port","arc","optical","bluetooth"]},
            "value":       {"label": "Value",           "icon": "rupee",   "keywords": ["price","value","worth","money","cost","budget"]},
        },
    },

    "kitchen": {
        "label": "Kitchen appliance",
        "url_keywords": ["pressure-cooker","cooker","mixer-grinder","mixer","grinder","blender","kettle","induction","microwave","oven","toaster","-otg-","oven-toaster"],
        "title_keywords": ["pressure cooker","mixer","grinder","kettle","induction","microwave","oven"],
        "aspects": {
            "build":       {"label": "Build quality",   "icon": "shield",  "keywords": ["build","material","steel","stainless","plastic","sturdy","handle","lid","gasket"]},
            "capacity":    {"label": "Capacity & size", "icon": "scale",   "keywords": ["capacity","size","litre","liter","big","small","family","fits"]},
            "performance": {"label": "Performance",     "icon": "spark",   "keywords": ["cooking","cooks","performance","fast","slow","power","watt","heating","whistle"]},
            "ease":        {"label": "Ease of use",     "icon": "tap",     "keywords": ["easy","use","clean","cleaning","wash","operate","handle","lid"]},
            "durability":  {"label": "Durability",      "icon": "clock",   "keywords": ["durable","long lasting","broke","broken","crack","damage","rust","year"]},
            "safety":      {"label": "Safety",          "icon": "shield",  "keywords": ["safe","safety","leak","accident","valve","whistle","secure"]},
            "value":       {"label": "Value",           "icon": "rupee",   "keywords": ["price","value","worth","money","cost","budget"]},
        },
    },

    "mattress": {
        "label": "Mattress / bedding",
        "url_keywords": ["mattress","bed-","memory-foam","spring-mattress","orthopedic"],
        "title_keywords": ["mattress","memory foam","orthopedic","spring"],
        "aspects": {
            "comfort":    {"label": "Comfort",      "icon": "bed",   "keywords": ["comfort","cozy","comfy","soft","plush","relax"]},
            "firmness":   {"label": "Firmness",     "icon": "ruler", "keywords": ["firm","firmness","soft","hard","medium","stiff","sinking"]},
            "support":    {"label": "Back support", "icon": "spark", "keywords": ["back","support","spine","posture","pain","ache","orthopedic"]},
            "size":       {"label": "Size & fit",   "icon": "ruler", "keywords": ["size","queen","king","single","double","fit","dimension","inch","cm"]},
            "durability": {"label": "Durability",   "icon": "clock", "keywords": ["durable","long lasting","sag","sagging","year","wear"]},
            "smell":      {"label": "Smell / off-gas","icon":"drop", "keywords": ["smell","odor","odour","chemical","new"]},
            "delivery":   {"label": "Delivery",     "icon": "bag",   "keywords": ["delivery","box","unpack","unbox","shipping"]},
            "value":      {"label": "Value",        "icon": "rupee", "keywords": ["price","value","worth","money","cost","budget"]},
        },
    },

    "footwear": {
        "label": "Footwear",
        "url_keywords": ["shoe","sneaker","sandal","slipper","boots","loafer","heels","flip-flop","running-shoe","sports-shoe"],
        "title_keywords": ["shoe","sneaker","sandal","loafer","slippers","running"],
        "aspects": {
            "fit":        {"label": "Fit & sizing",  "icon": "ruler",  "keywords": ["fit","size","sizing","tight","loose","narrow","wide","small","large"]},
            "comfort":    {"label": "Comfort",       "icon": "diamond","keywords": ["comfort","comfy","cushion","soft","wear","pain","blister"]},
            "build":      {"label": "Build quality", "icon": "shield", "keywords": ["build","material","stitch","sole","quality","glue","upper","leather"]},
            "durability": {"label": "Durability",    "icon": "clock",  "keywords": ["durable","torn","broken","worn","year","month","wear out"]},
            "look":       {"label": "Look & design", "icon": "shoe",   "keywords": ["look","design","colour","color","style","appear","picture","photo"]},
            "grip":       {"label": "Grip / sole",   "icon": "spark",  "keywords": ["grip","traction","slip","sole","slippery","floor"]},
            "value":      {"label": "Value",         "icon": "rupee",  "keywords": ["price","value","worth","money","cost","budget"]},
        },
    },

    "apparel": {
        "label": "Apparel / clothing",
        "url_keywords": ["t-shirt","tshirt","shirt","jeans","trouser","kurta","saree","dress","jacket","sweater","top-","kurti"],
        "title_keywords": ["t-shirt","shirt","jeans","kurta","saree","dress","jacket"],
        "aspects": {
            "fit":        {"label": "Fit & sizing",   "icon": "ruler",  "keywords": ["fit","size","sizing","tight","loose","slim","regular","small","large","oversized"]},
            "fabric":     {"label": "Fabric quality", "icon": "shirt",  "keywords": ["fabric","material","cotton","polyester","cloth","stitch","quality","feel"]},
            "color":      {"label": "Colour & print", "icon": "drop",   "keywords": ["colour","color","print","design","fade","shade"]},
            "comfort":    {"label": "Comfort",        "icon": "diamond","keywords": ["comfort","comfy","wear","skin","irritation"]},
            "durability": {"label": "Durability",     "icon": "clock",  "keywords": ["durable","wash","shrink","tear","worn","year"]},
            "look":       {"label": "Look",           "icon": "spark",  "keywords": ["look","stylish","appear","picture","photo","image","matches"]},
            "value":      {"label": "Value",          "icon": "rupee",  "keywords": ["price","value","worth","money","cost","budget"]},
        },
    },

    "bag": {
        "label": "Bag / luggage / backpack",
        "url_keywords": ["backpack","bag-","luggage","trolley","handbag","sling-bag","laptop-bag","duffel"],
        "title_keywords": ["backpack","luggage","handbag","duffel","sling"],
        "aspects": {
            "build":       {"label": "Build quality",   "icon": "shield", "keywords": ["build","material","stitch","zip","zipper","stitching","quality","fabric"]},
            "capacity":    {"label": "Capacity",        "icon": "scale",  "keywords": ["capacity","size","litre","liter","big","small","fits","spacious","compartment"]},
            "comfort":     {"label": "Strap / comfort", "icon": "diamond","keywords": ["strap","shoulder","comfort","padding","carry","weight"]},
            "durability":  {"label": "Durability",      "icon": "clock",  "keywords": ["durable","torn","tear","broke","year","wear","stitching"]},
            "look":        {"label": "Look",            "icon": "bag",    "keywords": ["look","design","colour","color","style","appear","picture"]},
            "waterproof":  {"label": "Water resistance","icon": "drop",   "keywords": ["water","rain","waterproof","resistant","dry","wet"]},
            "value":       {"label": "Value",           "icon": "rupee",  "keywords": ["price","value","worth","money","cost","budget"]},
        },
    },

    "skincare": {
        "label": "Skincare / personal care",
        "url_keywords": ["cream","lotion","shampoo","conditioner","face-wash","moisturizer","serum","sunscreen","soap","perfume","deodorant","oil"],
        "title_keywords": ["cream","lotion","shampoo","face wash","moisturizer","serum","sunscreen","perfume"],
        "aspects": {
            "effectiveness": {"label": "Effectiveness", "icon": "spark",   "keywords": ["work","effective","result","glow","skin","change","improve","help"]},
            "smell":         {"label": "Fragrance",     "icon": "drop",    "keywords": ["smell","fragrance","scent","perfume","aroma","odour","odor"]},
            "texture":       {"label": "Texture",       "icon": "diamond", "keywords": ["texture","feel","creamy","watery","sticky","greasy","oily","absorb","light","heavy"]},
            "skin":          {"label": "Skin reaction", "icon": "shield",  "keywords": ["skin","irritation","rash","allergy","break out","acne","sensitive","dry","oily"]},
            "packaging":     {"label": "Packaging",     "icon": "bag",     "keywords": ["package","pack","leak","bottle","seal","quantity","ml","gram"]},
            "value":         {"label": "Value",         "icon": "rupee",   "keywords": ["price","value","worth","money","cost","budget"]},
        },
    },

    "generic": {
        "label": "General product",
        "url_keywords": [],
        "title_keywords": [],
        "aspects": {
            "quality":      {"label": "Build quality",   "icon": "shield",  "keywords": ["quality","build","material","feel","premium","cheap","sturdy","flimsy"]},
            "performance":  {"label": "Performance",     "icon": "spark",   "keywords": ["work","working","performance","function","perform","fast","slow"]},
            "ease":         {"label": "Ease of use",     "icon": "tap",     "keywords": ["easy","use","operate","setup","install","convenient","simple","complicated"]},
            "design":       {"label": "Design / look",   "icon": "diamond", "keywords": ["design","look","appear","stylish","color","colour","picture","photo"]},
            "durability":   {"label": "Durability",      "icon": "clock",   "keywords": ["durable","long","year","month","broke","broken","damage","wear"]},
            "value":        {"label": "Value for money", "icon": "rupee",   "keywords": ["price","value","worth","money","cost","budget","cheap","expensive","vfm"]},
        },
    },
}


# -----------------------------------------------------------------------------
# Detection
# -----------------------------------------------------------------------------

def detect_category(url: str = "", title: str = "", sample_text: str = "") -> str:
    """Return the best-matching category key. Falls back to 'generic'."""
    haystack = " ".join([url or "", title or "", (sample_text or "")[:2000]]).lower()
    haystack = re.sub(r"[^a-z0-9 \-]", " ", haystack)

    scores: dict[str, int] = {}
    for key, cat in CATEGORIES.items():
        if key == "generic":
            continue
        s = 0
        for kw in cat["url_keywords"]:
            if kw in haystack:
                s += 3
        for kw in cat["title_keywords"]:
            if kw in haystack:
                s += 2
        # Aspect keyword density boost (content matches)
        for asp in cat["aspects"].values():
            for kw in asp["keywords"][:5]:
                if f" {kw} " in haystack:
                    s += 1
        if s:
            scores[key] = s

    if not scores:
        return "generic"
    return max(scores.items(), key=lambda kv: kv[1])[0]


def get_taxonomy(category_key: str) -> dict:
    return CATEGORIES.get(category_key, CATEGORIES["generic"])


def aspects_for(category_key: str) -> dict:
    return get_taxonomy(category_key)["aspects"]


# ─────────────────────────────────────────────────────────────────────────────
# USE-CASE TAXONOMY — what buyers actually use the product for
# Each category has its own list. Each use-case has a label, icon, and
# keywords that match in the review text.
# ─────────────────────────────────────────────────────────────────────────────

USE_CASES: dict[str, list[dict]] = {

    "earbuds": [
        {"label": "Music listening",        "icon": "speaker",
         "keywords": ["music", "song", "playlist", "audio quality", "bass", "listening", "spotify", "youtube music"]},
        {"label": "Office / video calls",   "icon": "phone",
         "keywords": ["office", "meeting", "zoom", "wfh", "work from home", "client call", "teams call", "google meet"]},
        {"label": "Workout & gym",          "icon": "headphones",
         "keywords": ["gym", "workout", "running", "exercise", "sweat", "treadmill", "cardio", "jog"]},
        {"label": "Travel & commute",       "icon": "diamond",
         "keywords": ["travel", "flight", "commute", "metro", "train", "journey", "airplane", "bus"]},
        {"label": "Gift / for someone",     "icon": "spark",
         "keywords": ["gift", "birthday", "anniversary", "for my mom", "for my dad", "wife", "husband", "friend", "cousin", "brother", "sister"]},
        {"label": "Gaming",                 "icon": "tap",
         "keywords": ["gaming", "pubg", "bgmi", "valorant", "fortnite", "low latency", "gaming mode"]},
    ],

    "smartphone": [
        {"label": "Photography",            "icon": "camera",
         "keywords": ["photo", "camera", "selfie", "portrait", "instagram", "picture quality", "low light", "night mode"]},
        {"label": "Gaming",                 "icon": "tap",
         "keywords": ["pubg", "bgmi", "game", "gaming", "fps", "fortnite", "free fire", "graphics", "valorant"]},
        {"label": "Work / productivity",    "icon": "phone",
         "keywords": ["work", "office", "business", "email", "documents", "presentation", "professional"]},
        {"label": "Social & messaging",     "icon": "spark",
         "keywords": ["whatsapp", "instagram", "facebook", "social media", "telegram", "snapchat"]},
        {"label": "Daily / heavy use",      "icon": "battery",
         "keywords": ["daily use", "all day", "heavy use", "intensive", "long hours"]},
        {"label": "Gift / for someone",     "icon": "spark",
         "keywords": ["gift", "birthday", "for my mom", "for my dad", "wife", "husband", "anniversary"]},
    ],

    "laptop": [
        {"label": "Work / WFH",             "icon": "phone",
         "keywords": ["work", "office", "wfh", "work from home", "client", "presentation", "meeting", "professional"]},
        {"label": "Study / education",      "icon": "diamond",
         "keywords": ["study", "college", "school", "online class", "exam", "student", "lecture", "tutorial"]},
        {"label": "Gaming",                 "icon": "tap",
         "keywords": ["gaming", "game", "fps", "graphics card", "rtx", "gtx", "fortnite", "cyberpunk"]},
        {"label": "Video / photo editing",  "icon": "camera",
         "keywords": ["edit", "video editing", "premiere", "photoshop", "lightroom", "render", "after effects"]},
        {"label": "Coding / development",   "icon": "cpu",
         "keywords": ["code", "coding", "programming", "developer", "ide", "vscode", "compiling"]},
        {"label": "Casual / browsing",      "icon": "wifi",
         "keywords": ["browsing", "netflix", "casual", "youtube", "watching", "movies"]},
    ],

    "smartwatch": [
        {"label": "Fitness tracking",       "icon": "spark",
         "keywords": ["fitness", "workout", "gym", "running", "steps", "exercise", "calorie", "heart rate", "spo2"]},
        {"label": "Sleep tracking",         "icon": "bed",
         "keywords": ["sleep", "snore", "rest", "bedtime"]},
        {"label": "Notifications",          "icon": "phone",
         "keywords": ["notification", "alert", "message", "whatsapp", "call alert"]},
        {"label": "Daily wear",             "icon": "diamond",
         "keywords": ["daily", "everyday", "all day", "office", "casual"]},
        {"label": "Gift",                   "icon": "spark",
         "keywords": ["gift", "birthday", "for my", "wife", "husband", "anniversary"]},
    ],

    "tv": [
        {"label": "Movies / Netflix",       "icon": "tv",
         "keywords": ["movie", "netflix", "amazon prime", "hotstar", "ott", "film"]},
        {"label": "Cricket / sports",       "icon": "spark",
         "keywords": ["cricket", "ipl", "sports", "match", "fifa", "football"]},
        {"label": "Gaming console",         "icon": "tap",
         "keywords": ["ps5", "xbox", "playstation", "gaming console", "console"]},
        {"label": "Family entertainment",   "icon": "diamond",
         "keywords": ["family", "kids", "children", "everyone", "guests"]},
        {"label": "News / daily TV",        "icon": "phone",
         "keywords": ["news", "daily", "channels", "cable", "set top box"]},
    ],

    "kitchen": [
        {"label": "Daily family cooking",   "icon": "pot",
         "keywords": ["family", "daily", "everyday", "regular use", "rice", "dal", "breakfast"]},
        {"label": "Single / small servings","icon": "diamond",
         "keywords": ["bachelor", "single", "small family", "couple", "two people"]},
        {"label": "Quick / fast cooking",   "icon": "spark",
         "keywords": ["quick", "fast", "instant", "minutes", "speed"]},
        {"label": "Party / large meals",    "icon": "scale",
         "keywords": ["guest", "party", "function", "gathering", "biryani", "feast"]},
        {"label": "Gift",                   "icon": "spark",
         "keywords": ["gift", "wedding", "for my mom", "wife", "anniversary"]},
    ],

    "mattress": [
        {"label": "Back / spine support",   "icon": "shield",
         "keywords": ["back pain", "back support", "spine", "posture", "orthopedic", "lumbar"]},
        {"label": "Side sleeper",           "icon": "bed",
         "keywords": ["side sleeper", "stomach sleeper", "back sleeper", "sleep position"]},
        {"label": "Couples",                "icon": "diamond",
         "keywords": ["husband", "wife", "couple", "two people", "spouse"]},
        {"label": "Kids",                   "icon": "spark",
         "keywords": ["kid", "child", "children", "baby", "son", "daughter"]},
        {"label": "Guest room",             "icon": "phone",
         "keywords": ["guest", "spare room", "occasional", "visitor"]},
    ],

    "footwear": [
        {"label": "Running",                "icon": "spark",
         "keywords": ["running", "jog", "marathon", "run"]},
        {"label": "Gym / training",         "icon": "headphones",
         "keywords": ["gym", "workout", "training", "lifting", "crossfit"]},
        {"label": "Daily / casual",         "icon": "diamond",
         "keywords": ["daily", "casual", "everyday", "all day", "office"]},
        {"label": "Travel / walking",       "icon": "shoe",
         "keywords": ["travel", "walking", "trekking", "hiking", "long walk"]},
        {"label": "Sports",                 "icon": "spark",
         "keywords": ["sport", "football", "cricket", "basketball", "tennis", "badminton"]},
        {"label": "Gift",                   "icon": "spark",
         "keywords": ["gift", "birthday", "for my"]},
    ],

    "apparel": [
        {"label": "Daily wear",             "icon": "shirt",
         "keywords": ["daily", "everyday", "casual", "regular"]},
        {"label": "Office / formal",        "icon": "phone",
         "keywords": ["office", "formal", "business", "interview", "professional"]},
        {"label": "Party / events",         "icon": "spark",
         "keywords": ["party", "wedding", "function", "ceremony", "occasion"]},
        {"label": "Gym / workout",          "icon": "headphones",
         "keywords": ["gym", "workout", "exercise", "yoga", "fitness"]},
        {"label": "Gift",                   "icon": "spark",
         "keywords": ["gift", "birthday", "for my mom", "wife", "husband", "anniversary"]},
    ],

    "bag": [
        {"label": "Office / laptop",        "icon": "phone",
         "keywords": ["office", "laptop", "work", "professional"]},
        {"label": "Travel",                 "icon": "diamond",
         "keywords": ["travel", "trip", "flight", "tour", "journey"]},
        {"label": "College / school",       "icon": "shirt",
         "keywords": ["college", "school", "student", "study"]},
        {"label": "Gym / sports",           "icon": "spark",
         "keywords": ["gym", "sport", "workout"]},
        {"label": "Gift",                   "icon": "spark",
         "keywords": ["gift", "birthday", "for my"]},
    ],

    "skincare": [
        {"label": "Daily skincare",         "icon": "drop",
         "keywords": ["daily", "morning", "night", "skincare routine", "regimen"]},
        {"label": "Acne / breakout",        "icon": "spark",
         "keywords": ["acne", "pimple", "breakout", "blemish", "spots"]},
        {"label": "Anti-aging",             "icon": "clock",
         "keywords": ["wrinkle", "fine line", "anti aging", "anti-aging", "young"]},
        {"label": "Sensitive skin",         "icon": "shield",
         "keywords": ["sensitive", "irritation", "allergy", "rash"]},
        {"label": "Gift",                   "icon": "spark",
         "keywords": ["gift", "birthday", "for my"]},
    ],

    "generic": [
        {"label": "Daily / regular use",    "icon": "diamond",
         "keywords": ["daily", "everyday", "regular", "all day", "frequent"]},
        {"label": "Occasional use",         "icon": "clock",
         "keywords": ["occasional", "sometimes", "rarely", "once a week"]},
        {"label": "Gift / for someone",     "icon": "spark",
         "keywords": ["gift", "birthday", "for my mom", "wife", "husband", "anniversary", "friend"]},
        {"label": "Family / shared use",    "icon": "shirt",
         "keywords": ["family", "kids", "children", "everyone", "shared"]},
        {"label": "Replacement / upgrade",  "icon": "spark",
         "keywords": ["replacement", "upgrade", "previous", "old one", "switching"]},
    ],
}


def use_cases_for(category_key: str) -> list[dict]:
    return USE_CASES.get(category_key, USE_CASES["generic"])


# ─────────────────────────────────────────────────────────────────────────────
# INDIAN CITY TIERS (used to classify reviewer geography)
# ─────────────────────────────────────────────────────────────────────────────

TIER1_CITIES = {
    "mumbai", "delhi", "new delhi", "bengaluru", "bangalore", "chennai",
    "kolkata", "calcutta", "hyderabad", "pune", "ahmedabad",
}

TIER2_CITIES = {
    # state capitals + large metros
    "jaipur", "lucknow", "kanpur", "nagpur", "indore", "bhopal", "patna",
    "ludhiana", "agra", "vadodara", "gurgaon", "gurugram", "noida", "ghaziabad",
    "faridabad", "coimbatore", "visakhapatnam", "vizag", "kochi", "cochin",
    "chandigarh", "dehradun", "mysore", "mysuru", "raipur", "ranchi",
    "guwahati", "thiruvananthapuram", "trivandrum", "bhubaneswar",
    "amritsar", "varanasi", "allahabad", "prayagraj", "meerut", "nashik",
    "rajkot", "vijayawada", "madurai", "jodhpur", "srinagar", "jamshedpur",
    "aurangabad", "dhanbad", "gwalior", "howrah", "asansol", "navi mumbai",
    "thane", "kalyan", "pimpri", "chinchwad", "solapur", "warangal",
    "guntur", "tiruchirappalli", "trichy", "tiruppur", "moradabad",
    "salem", "bareilly", "aligarh", "saharanpur", "siliguri", "guntakal",
    "jalandhar", "udaipur", "ajmer", "kota", "bikaner",
    "puducherry", "pondicherry", "shimla", "panaji", "gangtok", "imphal",
    "shillong", "kohima", "agartala", "aizawl", "itanagar",
    "surat",
}


def city_tier(city: str | None) -> str | None:
    if not city:
        return None
    c = city.strip().lower()
    if c in TIER1_CITIES:
        return "tier1"
    if c in TIER2_CITIES:
        return "tier2"
    return "tier3"
