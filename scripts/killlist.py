"""Append one rejection to data/killlist.csv.

APPEND-ONLY. This script opens the file in append mode and never rewrites,
reorders or deletes a row. A wrong row is corrected by appending a new one,
not by editing the old. The header is written only when the file is new.

reason_code must be one of REASON_CODES. date is the date of the decision
(when the hunt rejected it), not the date of any signal.
Unknown fields stay empty: an empty domain or source_url beats a guessed one.

    python scripts/killlist.py --date 2026-11-20 --company "Acme" \
        --domain acme.com --reason-code vendor --reason "scraping API" \
        --source-url https://acme.com
"""
import argparse
import csv
import os
import sys
from datetime import date

PATH = os.path.join("data", "killlist.csv")
HEADER = ["date", "company", "domain", "reason_code", "reason", "source_url"]
REASON_CODES = ("suppressed", "vendor", "wrong_buyer", "no_dated_signal",
                "no_evidenced_why", "off_icp")


def append(row: dict, path: str = PATH) -> None:
    code = (row.get("reason_code") or "").strip().lower()
    if code not in REASON_CODES:
        raise ValueError(f"reason_code {code!r} not one of {', '.join(REASON_CODES)}")
    date.fromisoformat(row["date"])  # ISO only; raises on anything else
    if not (row.get("company") or "").strip():
        raise ValueError("company is required")
    url = (row.get("source_url") or "").strip()
    if url and not url.startswith("http"):
        raise ValueError(f"source_url {url!r} is not an http URL")
    row = {**row, "reason_code": code}
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(HEADER)
        w.writerow([(row.get(k) or "").strip() for k in HEADER])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--date", required=True)
    p.add_argument("--company", required=True)
    p.add_argument("--domain", default="")
    p.add_argument("--reason-code", required=True, choices=REASON_CODES)
    p.add_argument("--reason", required=True)
    p.add_argument("--source-url", default="")
    a = p.parse_args(argv)
    try:
        append({"date": a.date, "company": a.company, "domain": a.domain,
                "reason_code": a.reason_code, "reason": a.reason,
                "source_url": a.source_url})
    except ValueError as e:
        print(f"REJECTED  {a.company}  {e}", file=sys.stderr)
        return 1
    print(f"KILLED    {a.company}  {a.reason_code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
