"""Schema, weights and id rules. Imported by every script. Standard library only.

Tier GATES, added 2026-11-20 after the second real run exposed them. These are
new rules, not threshold values changed to alter a result. The numeric tier
lines in TIERS (A 70, B 50, nurture 30) are unchanged.

  TIER_B_MIN_PAIN    An account cannot reach Tier B unless pain >= 5, whatever
                     its total. Implements the CLAUDE.md rule "No pain means
                     nurture at best", previously enforced only at pain == 0.
                     Exposed by Plush: fit fields alone (icp 30 + capacity 15
                     + reachability 15 = 60) put it in Tier B on pain 2.1.

  TIER_A_REQUIRES_EVIDENTIAL_SIGNAL / EVIDENTIAL_TYPES
                     Tier A needs at least one counted signal of an evidential
                     type (hiring, complaint) that is itself within
                     TIER_A_MAX_AGE_DAYS. Funding and launch say budget or
                     activity exists, not that this specific pain exists.
                     Exposed by Henfruit: Tier A on a single funding round.
                     The age rule closes the same defect at one remove: fresh
                     funding supplying the freshness while a stale hiring
                     signal supplies the evidentiality.
"""
import csv
import hashlib
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ACCOUNT_HEADERS = [
    "account_id", "company", "website", "country", "icp", "icp_confidence",
    "employees", "stage", "why_live_data", "decision_maker", "dm_title",
    "dm_source", "source_url", "first_seen", "notes",
]

SIGNAL_HEADERS = [
    "signal_id", "account_id", "signal_type", "signal_date", "captured_at",
    "evidence_url", "evidence_note", "date_confidence", "source_ref",
]

# The header signals.csv had before source_ref was added. ingest.py reads a
# file still carrying it and rewrites it with SIGNAL_HEADERS.
SIGNAL_HEADERS_V1 = SIGNAL_HEADERS[:-1]

# source_ref: optional. A short stable id for one item inside a source, such
# as an ATS job id when several postings share one board JSON endpoint.
SOURCE_REF = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

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

# gates, see module docstring; not thresholds
TIER_B_MIN_PAIN = 5
TIER_A_REQUIRES_EVIDENTIAL_SIGNAL = True
EVIDENTIAL_TYPES = frozenset({"hiring", "complaint"})

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


def signal_id(acct: str, signal_type: str, evidence_url: str, source_ref: str = "") -> str:
    """Account, type and URL, plus source_ref when one is given.

    Without source_ref the key, and so the id, is exactly what it was before
    the field existed, so every stored signal_id stays valid. With it, two
    postings behind one ATS JSON endpoint get two ids instead of colliding.
    """
    key = f"{acct}|{signal_type}|{(evidence_url or '').strip().lower()}"
    ref = (source_ref or "").strip()
    if ref:
        key += f"|{ref}"
    return "sg_" + hashlib.sha256(key.encode()).hexdigest()[:10]


# Suppression is defined once, here, and both ingest.py and score.py call it.
# If the two scripts disagreed about whether a domain is suppressed, the system
# would make two different claims about the same company: ingest would let it
# in while score rejects it, or the reverse. One definition makes that impossible.

def load_suppress(path="config/suppress.csv") -> dict:
    """Normalised domain -> reason. A relative path resolves from the repo root.
    A missing file means nothing is suppressed."""
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return {}
    table = {}
    with p.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            d = normalise_domain(row.get("domain", ""))
            if d:
                table[d] = (row.get("reason") or "").strip() or "no reason given"
    return table


def is_suppressed(domain: str, table: dict):
    """(matched_domain, reason) or None.

    Subdomain matching: a domain matches an entry if it equals it or ends with
    "." + entry, so jobs.openai.com is suppressed by openai.com. The input is
    normalised first, so a full URL is accepted too.
    """
    d = normalise_domain(domain)
    if not d:
        return None
    for entry, reason in table.items():
        if d == entry or d.endswith("." + entry):
            return entry, reason
    return None


def parse_date(s: str) -> date:
    """ISO only. Raises on anything else, deliberately."""
    return date.fromisoformat((s or "").strip()[:10])