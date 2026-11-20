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
    # Tier A freshness: exactly 90 days is inside the window. Uses hiring +
    # funding so the evidential gate passes and only freshness is under test.
    ("freshest 90 days", "account",
     (acct("d90", **NAMED), [sig("d90", "funding", 90, 1), sig("d90", "hiring", 90, 2)]),
     "A", {"freshest_days": "90"}),
    # Tier A freshness: 91 days is outside the window, demoted to B
    ("freshest 91 days", "account",
     (acct("d91", **NAMED), [sig("d91", "funding", 91, 1), sig("d91", "hiring", 91, 2)]),
     "B", {"freshest_days": "91"}),
    # Tier B pain gate: pain 4.9 at total 60 is below TIER_B_MIN_PAIN, nurture
    ("B gate pain 4.9, total 60", "decide", (60.0, 4.9, 10), "nurture", {"pain": "4.9"}),
    # Tier B pain gate: pain 5.0 at total 60 meets it, Tier B
    ("B gate pain 5.0, total 60", "decide", (60.0, 5.0, 10), "B", {"pain": "5.0"}),
    # Tier B pain gate: 4.95 ties up to 5.0 and passes
    ("B gate pain 4.95, total 60", "decide", (60.0, 4.95, 10), "B", {"pain": "5.0"}),
    # Tier B pain gate outranks a Tier-A total: 80 with pain 4.9 is still nurture
    ("B gate pain 4.9, total 80", "decide", (80.0, 4.9, 10), "nurture", {}),
    # Evidential gate, identical numbers: funding only is demoted to B
    ("A gate funding only", "decide", (75.0, 20.0, 10, {"funding"}), "B", {}),
    # Evidential gate, identical numbers: funding plus hiring reaches A
    ("A gate funding+hiring", "decide", (75.0, 20.0, 10, {"funding", "hiring"}), "A", {}),
    # Evidential gate, identical numbers: complaint is evidential too
    ("A gate launch+complaint", "decide", (75.0, 20.0, 10, {"launch", "complaint"}), "A", {}),
    # Evidential gate, real path: one fresh funding round, total over 70, is B
    ("A gate funding only, real", "account",
     (acct("fo", **NAMED), [sig("fo", "funding", 1, 1)]),
     "B", {"pain": "15.9", "score": "75.9"}),
    # Evidential gate, real path: same funding plus a hiring signal is A
    ("A gate fund+hire, real", "account",
     (acct("fh", **NAMED), [sig("fh", "funding", 1, 1), sig("fh", "hiring", 1, 2)]),
     "A", {}),
    # Evidential age: hiring at exactly 90 days plus fresh funding reaches A
    ("A gate hiring 90 + fund 1", "account",
     (acct("h90", **NAMED), [sig("h90", "funding", 1, 1), sig("h90", "hiring", 90, 2)]),
     "A", {"freshest_days": "1"}),
    # Evidential age: hiring at 91 days plus fresh funding is demoted, and the
    # reason names the evidential signal's own age, not the freshest overall
    ("A gate hiring 91 + fund 1", "account",
     (acct("h91", **NAMED), [sig("h91", "funding", 1, 1), sig("h91", "hiring", 91, 2)]),
     "B", {"freshest_days": "1",
           "reason_has": "freshest evidential signal (hiring) is 91 days old"}),
    # Evidential gate: a future-dated hiring signal does not count, so no A
    ("A gate future hiring", "account",
     (acct("fh2", **NAMED), [sig("fh2", "funding", 1, 1), sig("fh2", "hiring", -3, 2)]),
     "B", {}),
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
        # optional 4th item: signal types that counted, as a set (each aged at
        # `freshest`) or a {type: age} dict. Default is hiring at `freshest`,
        # so pre-gate cases keep testing only what they were written to test.
        total_raw, pain_raw, freshest, *rest = inputs
        given = rest[0] if rest else {"hiring"}
        ages = dict(given) if isinstance(given, dict) else {t: freshest for t in given}
        total, pain, tier, reason = score.decide(acct("x"), SUPPRESS, total_raw,
                                                 pain_raw, freshest, ages)
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
            if k == "reason_has":
                if v not in got["reason"]:
                    problems.append(f"reason lacks {v!r}")
            elif got[k] != v:
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
