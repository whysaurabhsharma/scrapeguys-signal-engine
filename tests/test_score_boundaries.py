"""Boundary self-check for scripts/score.py.

Builds every row in memory and writes no files. Prints PASS or FAIL per case
against an expected tier and exits 1 if any case fails.

    python tests/test_score_boundaries.py
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import score  # noqa: E402

# fixed, never today, so the result cannot drift with the calendar
ASOF = date(2026, 11, 20)
SUPPRESS = {}

# icp high 30 + series_b 15 + named, sourced DM 15 = 60 before pain
NAMED = {"decision_maker": "Jane Doe", "dm_title": "CTO",
         "dm_source": "https://example.com/team"}


def acct(aid, **kw):
    row = {"account_id": aid, "company": aid, "website": f"https://{aid}.example.com",
           "icp": "ai", "icp_confidence": "high", "stage": "series_b",
           "decision_maker": "", "dm_title": "", "dm_source": ""}
    row.update(kw)
    return row


def sig(aid, stype, days_ago, n, conf="exact"):
    return {"signal_id": f"sg_{aid}_{n}", "account_id": aid, "signal_type": stype,
            "signal_date": (ASOF - timedelta(days=days_ago)).isoformat(),
            "captured_at": ASOF.isoformat(), "date_confidence": conf,
            "evidence_url": f"https://example.com/{aid}/{n}", "evidence_note": ""}


# (label, kind, inputs, expected tier, expected shown values)
# kind "decide": raw total/pain/freshest through score.decide, the real rounding path
# kind "account": full rows through score.score_account
CASES = [
    # Tier A threshold: 69.95 rounds up to 70.0 and crosses the line
    ("total 69.95", "decide", (69.95, 20.0, 10), "A", {"score": "70.0"}),
    # Tier A threshold: 70.04 rounds down to 70.0 and stays on the line
    ("total 70.04", "decide", (70.04, 20.0, 10), "A", {"score": "70.0"}),
    # Tier A min pain: 14.95 ties up to 15.0 and passes, never lost to float storage
    ("pain 14.95, total 75", "decide", (75.0, 14.95, 10), "A", {"pain": "15.0"}),
    # Tier A min pain: 14.94 rounds to 14.9 and fails, demoted to B
    ("pain 14.94, total 75", "decide", (75.0, 14.94, 10), "B", {"pain": "14.9"}),
    # Tier A freshness: exactly 90 days is inside the window
    ("freshest 90 days", "account",
     (acct("d90", **NAMED), [sig("d90", "funding", 90, 1), sig("d90", "launch", 90, 2)]),
     "A", {"freshest_days": "90"}),
    # Tier A freshness: 91 days is outside the window, demoted to B
    ("freshest 91 days", "account",
     (acct("d91", **NAMED), [sig("d91", "funding", 91, 1), sig("d91", "launch", 91, 2)]),
     "B", {"freshest_days": "91"}),
    # Pain-zero gate: a future-dated signal does not count, so fit alone caps at nurture
    ("future-dated only", "account",
     (acct("fut", **NAMED), [sig("fut", "funding", -5, 1)]),
     "nurture", {"pain": "0.0", "freshest_days": ""}),
    # Freshest-per-type: two hiring signals score the same as the stronger one alone
    ("two hiring signals", "account",
     (acct("hr2", **NAMED), [sig("hr2", "hiring", 5, 1), sig("hr2", "hiring", 30, 2)]),
     "A", {"pain": "17.0", "score": "77.0"}),
    # Freshest-per-type: baseline for the case above
    ("one hiring signal", "account",
     (acct("hr1", **NAMED), [sig("hr1", "hiring", 5, 1)]),
     "A", {"pain": "17.0", "score": "77.0"}),
]


def run_case(kind, inputs):
    if kind == "decide":
        total_raw, pain_raw, freshest = inputs
        total, pain, tier, reason = score.decide(acct("x"), SUPPRESS, total_raw,
                                                 pain_raw, freshest)
        return {"score": f"{total:.1f}", "pain": f"{pain:.1f}", "tier": tier,
                "reason": reason, "freshest_days": str(freshest)}
    a, sigs = inputs
    return score.score_account(a, sigs, SUPPRESS, ASOF)


def main() -> int:
    failures = 0
    for label, kind, inputs, want_tier, want in CASES:
        got = run_case(kind, inputs)
        problems = []
        if got["tier"] != want_tier:
            problems.append(f"tier {got['tier']} != {want_tier}")
        for k, v in want.items():
            if got[k] != v:
                problems.append(f"{k} {got[k]!r} != {v!r}")
        status = "FAIL" if problems else "PASS"
        failures += bool(problems)
        print(f"{status}  {label:22} score={got['score']:>5} pain={got['pain']:>4} "
              f"fresh={got['freshest_days'] or '-':>3} tier={got['tier']}")
        print(f"      {got['reason']}")
        for p in problems:
            print(f"      ! {p}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


def test_boundaries():
    """pytest entry point."""
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
