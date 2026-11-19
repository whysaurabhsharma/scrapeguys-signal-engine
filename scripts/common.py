"""Schema, weights and id rules. Imported by every script. Standard library only."""
import hashlib
import re
from datetime import date

ACCOUNT_HEADERS = [
    "account_id", "company", "website", "country", "icp", "icp_confidence",
    "employees", "stage", "why_live_data", "decision_maker", "dm_title",
    "dm_source", "source_url", "first_seen", "notes",
]

SIGNAL_HEADERS = [
    "signal_id", "account_id", "signal_type", "signal_date", "captured_at",
    "evidence_url", "evidence_note", "date_confidence",
]

SCORED_HEADERS = [
    "account_id", "company", "website", "icp", "score", "tier", "reason",
    "icp_match", "pain", "capacity", "reachability", "freshest_days",
]

ICPS = ("ai", "travel", "commerce")

# weight: contribution to pain at age zero. half_life: days to halve it.
SIGNAL_MODEL = {
    "hiring":    {"weight": 18, "half_life": 60},
    "funding":   {"weight": 16, "half_life": 120},
    "launch":    {"weight": 14, "half_life": 90},
    "complaint": {"weight": 12, "half_life": 45},
}

# how much we trust signal_date itself
DATE_CONFIDENCE = {
    "exact":   1.00,  # greenhouse first_published, funding announcement
    "ceiling": 0.75,  # ashby publishedAt: LAST published, may be a repost
    "approx":  0.50,  # dated page, no machine-readable field
}

CONFIDENCE = {"high": 30, "medium": 20, "low": 10}

STAGES = {
    "seed": 8, "series_a": 13, "series_b": 15, "series_c": 15,
    "growth": 15, "public": 10, "bootstrapped": 8, "unknown": 5,
}

TIERS = {"A": 70, "B": 50, "nurture": 30}
TIER_A_MIN_PAIN = 15
TIER_A_MAX_AGE_DAYS = 90

CEILINGS = {"icp_match": 30, "pain": 40, "capacity": 15, "reachability": 15}

NOISE = ("pvt", "private", "ltd", "limited", "inc", "llc", "corp", "technologies",
         "technology", "solutions", "labs", "systems", "india", "the", "co")


def normalise_domain(url: str) -> str:
    """scrapeguys.com from any of its URL forms. Lowercase, no www, no path."""
    d = (url or "").strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    d = d.split("/")[0].split("?")[0].split("#")[0]
    return d.rstrip(".")


def normalise_name(name: str) -> str:
    """For dedupe only. Lowercase, punctuation out, corporate noise words out."""
    n = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    return " ".join(w for w in n.split() if w not in NOISE)


def account_id(website: str) -> str:
    """Derived, never supplied. Same domain always gives the same id."""
    d = normalise_domain(website)
    return "ac_" + hashlib.sha256(d.encode()).hexdigest()[:10]


def signal_id(acct: str, signal_type: str, evidence_url: str) -> str:
    key = f"{acct}|{signal_type}|{(evidence_url or '').strip().lower()}"
    return "sg_" + hashlib.sha256(key.encode()).hexdigest()[:10]


def parse_date(s: str) -> date:
    """ISO only. Raises on anything else, deliberately."""
    return date.fromisoformat((s or "").strip()[:10])