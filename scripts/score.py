"""Score accounts deterministically from accounts.csv and signals.csv.

Reads data/accounts.csv and data/signals.csv, scores each account on ICP match,
decayed signal pain, capacity and reachability, assigns a tier with a written
reason, and writes data/scored.csv. Standard library only. Every weight,
threshold and ceiling comes from common.py; nothing is tuned here.

Scoring lives in Python, not the model, because the ranking has to be
reproducible and defensible, so nothing here is left to judgment.

Rounding: the total and pain are each rounded ONCE, to one decimal place, from
their unrounded values. Those rounded values drive the tier, the gates, the
reason text and the CSV, so the score shown is always the score decided on.
The four part columns are rounded separately for display, so they may not sum
exactly to the total, by at most 0.2.

Ties round up (ROUND_HALF_UP via Decimal), deterministically, so a boundary
case such as pain 14.95 never depends on how the float happens to be stored.

    python scripts/score.py [--asof YYYY-MM-DD] [--out PATH] [--quiet] [--no-log]
"""
import argparse
import csv
import os
import sys
from collections import Counter
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    ACCOUNT_HEADERS,
    CEILINGS,
    CONFIDENCE,
    DATE_CONFIDENCE,
    SCORED_HEADERS,
    SIGNAL_HEADERS,
    SIGNAL_MODEL,
    STAGES,
    TIER_A_MAX_AGE_DAYS,
    TIER_A_MIN_PAIN,
    TIERS,
    normalise_domain,
    parse_date,
)

ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS = ROOT / "data" / "accounts.csv"
SIGNALS = ROOT / "data" / "signals.csv"
SCORED = ROOT / "data" / "scored.csv"
SUPPRESS = ROOT / "config" / "suppress.csv"
RUNS_LOG = ROOT / "data" / "runs.log"

TIER_ORDER = ("A", "B", "nurture", "reject")

# pain at or below this is treated as zero; avoids exact float equality
PAIN_EPSILON = 1e-9


# ---------------------------------------------------------------- reading

def read_csv(path: Path, required: list) -> list:
    """Rows as dicts. Fails loudly if a contract column is missing."""
    if not path.exists():
        sys.exit(f"score.py: missing input {path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [h for h in required if h not in (reader.fieldnames or [])]
        if missing:
            sys.exit(f"score.py: {path.name} is missing columns: {', '.join(missing)}")
        return [{k: (v or "").strip() for k, v in row.items() if k} for row in reader]


def read_suppress(path: Path) -> dict:
    """normalised domain -> reason."""
    if not path.exists():
        return {}
    out = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            d = normalise_domain(row.get("domain", ""))
            if d:
                out[d] = (row.get("reason") or "").strip() or "no reason given"
    return out


# ---------------------------------------------------------------- scoring

def cap(name: str, value: float) -> float:
    return max(0.0, min(float(value), float(CEILINGS[name])))


def score_icp_match(acct: dict) -> float:
    return cap("icp_match", CONFIDENCE.get(acct.get("icp_confidence", "").lower(), 0))


def score_capacity(acct: dict) -> float:
    stage = acct.get("stage", "").lower() or "unknown"
    return cap("capacity", STAGES.get(stage, STAGES["unknown"]))


def score_reachability(acct: dict) -> float:
    name = acct.get("decision_maker", "")
    source = acct.get("dm_source", "")
    title = acct.get("dm_title", "")
    if name and source:
        return cap("reachability", 15)
    if title and not name:
        return cap("reachability", 7)
    return cap("reachability", 0)


def decayed(sig: dict, asof: date):
    """(value, age_days) for one signal, or None if it cannot count.

    A signal dated after the as-of date did not exist yet on that date, so it
    is ignored rather than clamped to age zero.
    """
    model = SIGNAL_MODEL.get(sig.get("signal_type", "").lower())
    if model is None:
        return None
    try:
        when = parse_date(sig.get("signal_date", ""))
    except ValueError:
        return None
    age = (asof - when).days
    if age < 0:
        return None
    conf_key = sig.get("date_confidence", "").lower()
    conf = DATE_CONFIDENCE.get(conf_key, DATE_CONFIDENCE["approx"])
    value = model["weight"] * 0.5 ** (age / model["half_life"]) * conf
    return value, age


def score_pain(signals: list, asof: date):
    """(pain, freshest_days, per_type).

    Per signal type only the single strongest decayed signal counts: five
    postings for one role are one fact. Types are then summed and capped.
    """
    best = {}
    freshest = None
    for sig in signals:
        got = decayed(sig, asof)
        if got is None:
            continue
        value, age = got
        stype = sig["signal_type"].lower()
        if value > best.get(stype, -1.0):
            best[stype] = value
        if freshest is None or age < freshest:
            freshest = age
    return cap("pain", sum(best.values())), freshest, best


# ---------------------------------------------------------------- tiers

def tier_for(acct: dict, suppress: dict, total: float, pain: float, freshest):
    """(tier, reason). Rules applied in a fixed order; first match wins.

    total and pain arrive already rounded once to one decimal place (see
    decide), so the tier is decided on exactly the numbers that are shown.
    """
    website = acct.get("website", "")
    domain = normalise_domain(website)

    # 1. no website
    if not domain:
        return "reject", "Rejected: no website on record, so the account cannot be identified."

    # 2. suppression list
    if domain in suppress:
        return "reject", f"Rejected: {domain} is on the suppression list ({suppress[domain]})."

    # 3. no pain
    if pain <= PAIN_EPSILON:
        if total >= TIERS["nurture"]:
            return "nurture", (f"Nurture: scores {total:.1f} on fit alone but has no live, "
                               "dated signal, so it cannot rank above nurture.")
        return "reject", (f"Rejected: no live, dated signal and a fit score of {total:.1f}, "
                          f"below the nurture line of {TIERS['nurture']}.")

    # 4. tier A threshold
    if total >= TIERS["A"]:
        failed = []
        if pain < TIER_A_MIN_PAIN:
            failed.append(f"pain is {pain:.1f}, below the Tier A minimum of {TIER_A_MIN_PAIN}")
        if freshest is None or freshest > TIER_A_MAX_AGE_DAYS:
            age = "unknown" if freshest is None else f"{freshest} days old"
            failed.append(f"the freshest signal is {age}, past the "
                          f"{TIER_A_MAX_AGE_DAYS}-day Tier A window")
        if not failed:
            return "A", (f"Tier A: scores {total:.1f} with pain {pain:.1f} and a signal "
                         f"{freshest} days old.")
        return "B", (f"Tier B: scores {total:.1f}, enough for A, but "
                     + " and ".join(failed) + ".")

    # 5. tier B
    if total >= TIERS["B"]:
        return "B", (f"Tier B: scores {total:.1f}, between {TIERS['B']} and {TIERS['A']}; "
                     f"freshest signal {freshest} days old.")

    # 6. nurture
    if total >= TIERS["nurture"]:
        return "nurture", (f"Nurture: scores {total:.1f}, below the Tier B line of "
                           f"{TIERS['B']}; freshest signal {freshest} days old.")

    # 7. reject
    return "reject", (f"Rejected: scores {total:.1f}, below the nurture line of "
                      f"{TIERS['nurture']}.")


def round1(x: float) -> float:
    """One decimal place, ties up. str() first so 14.95 is 14.95, not 14.9499..."""
    return float(Decimal(str(x)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def decide(acct: dict, suppress: dict, total_raw: float, pain_raw: float, freshest):
    """(total, pain, tier, reason). Rounds total and pain once, then decides on them."""
    total = round1(total_raw)
    pain = round1(pain_raw)
    tier, reason = tier_for(acct, suppress, total, pain, freshest)
    return total, pain, tier, reason


def score_account(acct: dict, signals: list, suppress: dict, asof: date) -> dict:
    icp_raw = score_icp_match(acct)
    pain_raw, freshest, _ = score_pain(signals, asof)
    capacity_raw = score_capacity(acct)
    reach_raw = score_reachability(acct)
    total_raw = icp_raw + pain_raw + capacity_raw + reach_raw

    total, pain, tier, reason = decide(acct, suppress, total_raw, pain_raw, freshest)

    # remaining parts rounded for display only; may differ from total by <= 0.2
    icp_match = round1(icp_raw)
    capacity = round1(capacity_raw)
    reach = round1(reach_raw)

    return {
        "account_id": acct.get("account_id", ""),
        "company": acct.get("company", ""),
        "website": acct.get("website", ""),
        "icp": acct.get("icp", ""),
        "score": f"{total:.1f}",
        "tier": tier,
        "reason": reason,
        "icp_match": f"{icp_match:.1f}",
        "pain": f"{pain:.1f}",
        "capacity": f"{capacity:.1f}",
        "reachability": f"{reach:.1f}",
        "freshest_days": "" if freshest is None else str(freshest),
    }


# ---------------------------------------------------------------- output

def write_scored(rows: list, out: Path) -> None:
    """Write via a temp file and replace, so a crash never leaves half a CSV."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SCORED_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, out)


def append_log(asof: date, counts: Counter, out: Path) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    tiers = " ".join(f"{t}={counts.get(t, 0)}" for t in TIER_ORDER)
    line = f"{stamp}\tscore.py\tasof={asof.isoformat()}\t{tiers}\tout={out}\n"
    with RUNS_LOG.open("a", encoding="utf-8", newline="") as f:
        f.write(line)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Score accounts into scored.csv.")
    p.add_argument("--asof", help="as-of date, YYYY-MM-DD (default: today)")
    p.add_argument("--out", default=str(SCORED), help="output CSV path")
    p.add_argument("--quiet", action="store_true", help="no summary on stdout")
    p.add_argument("--no-log", action="store_true", help="do not append to data/runs.log")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        asof = parse_date(args.asof) if args.asof else date.today()
    except ValueError:
        sys.exit(f"score.py: --asof must be YYYY-MM-DD, got {args.asof!r}")
    out = Path(args.out)

    accounts = read_csv(ACCOUNTS, ACCOUNT_HEADERS)
    signals = read_csv(SIGNALS, SIGNAL_HEADERS)
    suppress = read_suppress(SUPPRESS)

    by_account = {}
    for sig in signals:
        by_account.setdefault(sig.get("account_id", ""), []).append(sig)

    rows = [score_account(a, by_account.get(a.get("account_id", ""), []), suppress, asof)
            for a in accounts]
    # score descending, then account_id ascending as a stable tie-break
    rows.sort(key=lambda r: r["account_id"])
    rows.sort(key=lambda r: float(r["score"]), reverse=True)

    write_scored(rows, out)
    counts = Counter(r["tier"] for r in rows)

    if not args.no_log:
        append_log(asof, counts, out)

    if not args.quiet:
        tiers = ", ".join(f"{t} {counts.get(t, 0)}" for t in TIER_ORDER)
        print(f"Scored {len(rows)} accounts as of {asof.isoformat()}: {tiers}.")
        print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
