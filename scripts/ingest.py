"""Ingest staged JSON into data/accounts.csv and data/signals.csv.

The ONLY writer of those two files. Standard library only. Schema, ids and
date parsing come from common.py; nothing about the contract is decided here.

Input: one or more JSON files in data/staging/, each a list of account objects
shaped like data/staging/EXAMPLE.json, with a "signals" list inside. With no
file arguments, every *.json in data/staging/ except EXAMPLE.json is read.

Validation: every rejected account or signal prints a REJECTED line naming the
record, the field and the reason. Nothing is dropped silently. Ids, first_seen
and any unknown keys found in the input are ignored, and each is reported.

Idempotency, the property this script exists for:
  - an account is keyed by account_id, derived from the normalised domain.
    One already present is updated in place, never duplicated.
  - on update, a non-empty incoming value replaces the stored one; an empty
    incoming value leaves the stored one alone. Ingest never blanks a field.
    decision_maker, dm_title and dm_source move as one unit, so a name is
    never left attached to someone else's source.
  - a signal whose signal_id is already present is skipped as a duplicate.
  - first_seen is set on first write and never overwritten.
  - captured_at is set to the run date when absent.
  - existing rows keep their order and bytes; new rows are appended. If
    nothing changed, the CSVs are not rewritten at all, so running the same
    file twice leaves both byte-identical.

    python scripts/ingest.py [FILE ...] [--asof YYYY-MM-DD] [--dry-run]
                             [--quiet] [--no-log]
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    ACCOUNT_HEADERS,
    DATE_CONFIDENCE,
    ICPS,
    SIGNAL_HEADERS,
    SIGNAL_MODEL,
    account_id,
    is_suppressed,
    load_suppress,
    normalise_domain,
    parse_date,
    signal_id,
)

ROOT = Path(__file__).resolve().parent.parent
STAGING = ROOT / "data" / "staging"
ACCOUNTS = ROOT / "data" / "accounts.csv"
SIGNALS = ROOT / "data" / "signals.csv"
SUPPRESS = ROOT / "config" / "suppress.csv"
RUNS_LOG = ROOT / "data" / "runs.log"

EXAMPLE_NAME = "EXAMPLE.json"

# strict YYYY-MM-DD; parse_date alone would accept "2026-08-24 junk"
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# derived or stamped by this script; if the input supplies them, they are ignored
ACCOUNT_DERIVED = ("account_id", "first_seen")
SIGNAL_DERIVED = ("signal_id", "account_id")

ACCOUNT_INPUT = [h for h in ACCOUNT_HEADERS if h not in ACCOUNT_DERIVED]
SIGNAL_INPUT = [h for h in SIGNAL_HEADERS if h not in SIGNAL_DERIVED]

# enum-like fields compared case-insensitively and stored lowercase
LOWERCASE = {"icp", "icp_confidence", "stage", "signal_type", "date_confidence"}

DM_FIELDS = ("decision_maker", "dm_title", "dm_source")


class Report:
    """Collects counts and prints per-record lines. REJECTED always prints."""

    def __init__(self, quiet: bool):
        self.quiet = quiet
        self.accounts_rejected = 0
        self.signals_rejected = 0

    def rejected(self, who: str, errors: list, kind: str) -> None:
        """Print every (field, why) for one record; count the record once."""
        for field, why in errors:
            print(f"REJECTED  {who}  field={field}  {why}")
        if kind == "account":
            self.accounts_rejected += 1
        else:
            self.signals_rejected += 1

    def note(self, who: str, msg: str) -> None:
        if not self.quiet:
            print(f"NOTE      {who}  {msg}")

    def info(self, tag: str, who: str, msg: str = "") -> None:
        if not self.quiet:
            print(f"{tag:<9} {who}  {msg}".rstrip())

    @property
    def records_rejected(self) -> int:
        return self.accounts_rejected + self.signals_rejected


# ---------------------------------------------------------------- reading

def clean(value, field: str = "") -> str:
    """JSON value to a stripped CSV string. None is empty."""
    if value is None:
        return ""
    s = str(value).strip()
    return s.lower() if field in LOWERCASE else s


def read_table(path: Path, headers: list) -> list:
    """Existing rows verbatim, as dicts. The header must match exactly."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []
        if list(reader.fieldnames) != list(headers):
            sys.exit(f"ingest.py: {path.name} header does not match common.py.\n"
                     f"  found:    {','.join(reader.fieldnames)}\n"
                     f"  expected: {','.join(headers)}")
        return [dict(row) for row in reader]


def resolve_inputs(names: list) -> list:
    """Input files, all inside data/staging/. Aborts before any write if not."""
    staging = STAGING.resolve()
    if not names:
        files = sorted(p for p in staging.glob("*.json") if p.name != EXAMPLE_NAME)
        if not files:
            sys.exit(f"ingest.py: no JSON files in {STAGING} (EXAMPLE.json is skipped)")
        return files
    files = []
    for n in names:
        p = Path(n).resolve()
        try:
            p.relative_to(staging)
        except ValueError:
            sys.exit(f"ingest.py: {n} is not inside {STAGING}; stage it there first")
        if not p.is_file():
            sys.exit(f"ingest.py: {n} does not exist")
        files.append(p)
    return files


def load_json(path: Path) -> list:
    """A whole file is structurally valid or the run aborts before writing."""
    try:
        with path.open(encoding="utf-8-sig") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"ingest.py: {path.name} is not valid JSON: {e}")
    if not isinstance(data, list):
        sys.exit(f"ingest.py: {path.name} must be a JSON list of accounts, "
                 f"got {type(data).__name__}")
    return data


# ---------------------------------------------------------------- validation

def check_date(raw: str, field: str):
    """(date, None) or (None, reason)."""
    if not raw:
        return None, f"{field} is missing"
    if not ISO_DATE.match(raw):
        return None, f"{field} {raw!r} is not an ISO date (YYYY-MM-DD)"
    try:
        return parse_date(raw), None
    except ValueError:
        return None, f"{field} {raw!r} is not a real calendar date"


def validate_signal(raw, acct: str, who: str, asof: date, run_date: str, rep: Report):
    """One signal row, or None after printing every reason it fails."""
    if not isinstance(raw, dict):
        rep.rejected(who, [("signals", f"entry is {type(raw).__name__}, not an object")], "signal")
        return None

    for k in SIGNAL_DERIVED:
        if k in raw:
            rep.note(who, f"{k} supplied in input; ignored, ingest.py derives it")
    for k in sorted(set(raw) - set(SIGNAL_INPUT) - set(SIGNAL_DERIVED)):
        rep.note(who, f"unknown key {k!r}; ignored")

    s = {k: clean(raw.get(k), k) for k in SIGNAL_INPUT}
    errors = []

    if s["signal_type"] not in SIGNAL_MODEL:
        errors.append(("signal_type", f"{s['signal_type']!r} is not one of "
                                      f"{', '.join(SIGNAL_MODEL)}"))

    url = s["evidence_url"]
    if not url:
        errors.append(("evidence_url", "is missing"))
    elif not url.lower().startswith(("http://", "https://")):
        errors.append(("evidence_url", f"{url!r} does not start with http"))

    when, why = check_date(s["signal_date"], "signal_date")
    if why:
        errors.append(("signal_date", why))
    elif when > asof:
        errors.append(("signal_date", f"{s['signal_date']} is after --asof "
                                      f"{asof.isoformat()}; a signal cannot be from the future"))

    if s["captured_at"]:
        _, why = check_date(s["captured_at"], "captured_at")
        if why:
            errors.append(("captured_at", why))

    if errors:
        rep.rejected(who, errors, "signal")
        return None

    if s["date_confidence"] not in DATE_CONFIDENCE:
        rep.note(who, f"date_confidence {s['date_confidence']!r} is not one of "
                      f"{', '.join(DATE_CONFIDENCE)}; score.py will treat it as approx")
    if not s["captured_at"]:
        s["captured_at"] = run_date

    row = {h: "" for h in SIGNAL_HEADERS}
    row.update(s)
    row["account_id"] = acct
    row["signal_id"] = signal_id(acct, s["signal_type"], url)
    return row


def validate_account(raw, where: str, suppress: dict, asof: date, run_date: str,
                     rep: Report):
    """(account row, [signal rows]) or None after printing every reason it fails.

    Account-level checks run first and are all reported together. Signals are
    validated only for an account that passes them.
    """
    if not isinstance(raw, dict):
        rep.rejected(where, [("record", f"is {type(raw).__name__}, not an object")], "account")
        return None

    company = clean(raw.get("company")) or "(no company)"
    who = f"{company} [{where}]"

    for k in ACCOUNT_DERIVED:
        if k in raw:
            rep.note(who, f"{k} supplied in input; ignored, ingest.py derives it")
    for k in sorted(set(raw) - set(ACCOUNT_INPUT) - set(ACCOUNT_DERIVED) - {"signals"}):
        rep.note(who, f"unknown key {k!r}; ignored")

    a = {k: clean(raw.get(k), k) for k in ACCOUNT_INPUT}
    errors = []

    domain = normalise_domain(a["website"])
    if not a["website"]:
        errors.append(("website", "is missing"))
    elif not domain:
        errors.append(("website", f"{a['website']!r} normalises to an empty domain"))
    else:
        hit = is_suppressed(domain, suppress)
        if hit:
            errors.append(("website", f"{domain} is suppressed: {hit[0]} ({hit[1]})"))

    if a["icp"] not in ICPS:
        errors.append(("icp", f"{a['icp']!r} is not one of {', '.join(ICPS)}"))

    if a["decision_maker"]:
        if not a["dm_source"]:
            errors.append(("dm_source", f"decision_maker {a['decision_maker']!r} "
                                        "is named without a dm_source"))
        elif not a["dm_source"].lower().startswith(("http://", "https://")):
            errors.append(("dm_source", f"{a['dm_source']!r} is not a public URL"))

    sigs_raw = raw.get("signals")
    if not isinstance(sigs_raw, list):
        errors.append(("signals", "is missing or not a list"))

    if errors:
        rep.rejected(who, errors, "account")
        return None

    acct = account_id(a["website"])
    good = []
    for j, s in enumerate(sigs_raw, start=1):
        row = validate_signal(s, acct, f"{who} signal {j}", asof, run_date, rep)
        if row is not None:
            good.append(row)

    if not good:
        rep.rejected(who, [("signals", f"no valid signal survived ({len(sigs_raw)} given)")],
                     "account")
        return None

    row = {h: "" for h in ACCOUNT_HEADERS}
    row.update(a)
    row["account_id"] = acct
    return row, good


# ---------------------------------------------------------------- merge

def merge_account(existing: dict, incoming: dict) -> list:
    """Update existing in place. Returns the changed field names.

    Non-empty incoming replaces; empty incoming leaves alone. account_id and
    first_seen are never touched. The decision-maker fields move as a unit.
    """
    changed = []
    for h in ACCOUNT_HEADERS:
        if h in ACCOUNT_DERIVED or h in DM_FIELDS:
            continue
        new = incoming[h]
        if new and new != existing[h]:
            existing[h] = new
            changed.append(h)

    if incoming["decision_maker"]:
        # a named, sourced DM replaces the whole trio, title included
        for h in DM_FIELDS:
            if incoming[h] != existing[h]:
                existing[h] = incoming[h]
                changed.append(h)
    elif incoming["dm_title"] and not existing["decision_maker"]:
        # a bare title only fills in where no named person is on record
        if incoming["dm_title"] != existing["dm_title"]:
            existing["dm_title"] = incoming["dm_title"]
            changed.append("dm_title")
    return changed


def merge(accounts: list, signals: list, validated: list, run_date: str, rep: Report):
    """Fold validated records into the existing rows. Mutates both lists."""
    by_id = {r["account_id"]: r for r in accounts}
    seen_signals = {r["signal_id"] for r in signals}
    added, updated = set(), set()
    signals_added = signals_dup = 0

    for acct_row, sig_rows in validated:
        aid = acct_row["account_id"]
        who = f"{acct_row['company'] or '(no company)'} {aid}"
        existing = by_id.get(aid)
        if existing is None:
            acct_row["first_seen"] = run_date
            accounts.append(acct_row)
            by_id[aid] = acct_row
            added.add(aid)
            rep.info("ADDED", who)
        else:
            changed = merge_account(existing, acct_row)
            if changed:
                if aid not in added:
                    updated.add(aid)
                rep.info("UPDATED", who, "fields: " + ", ".join(changed))
            else:
                rep.info("UNCHANGED", who)

        for s in sig_rows:
            sid = s["signal_id"]
            if sid in seen_signals:
                signals_dup += 1
                rep.info("DUPLICATE", f"{who} {sid}", f"{s['signal_type']} {s['evidence_url']}")
                continue
            signals.append(s)
            seen_signals.add(sid)
            signals_added += 1
            rep.info("SIGNAL", f"{who} {sid}", f"{s['signal_type']} {s['signal_date']}")

    return {
        "accounts_added": len(added),
        "accounts_updated": len(updated),
        "signals_added": signals_added,
        "signals_duplicate": signals_dup,
    }


# ---------------------------------------------------------------- output

def write_table(rows: list, headers: list, out: Path) -> Path:
    """Write to a temp file and return it; the caller replaces."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    return tmp


def append_log(asof: date, files: list, counts: dict) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    names = ",".join(p.name for p in files)
    parts = "\t".join(f"{k}={v}" for k, v in counts.items())
    line = f"{stamp}\tingest.py\tasof={asof.isoformat()}\tfiles={names}\t{parts}\n"
    with RUNS_LOG.open("a", encoding="utf-8", newline="") as f:
        f.write(line)


def print_summary(counts: dict, rep: Report, dry_run: bool) -> None:
    head = "Summary (dry run, nothing written):" if dry_run else "Summary:"
    print(head)
    print(f"  accounts added       {counts['accounts_added']}")
    print(f"  accounts updated     {counts['accounts_updated']}")
    print(f"  signals added        {counts['signals_added']}")
    print(f"  signals duplicate    {counts['signals_duplicate']}")
    print(f"  records rejected     {counts['records_rejected']}  "
          f"({rep.accounts_rejected} accounts, {rep.signals_rejected} signals)")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Ingest staged JSON into accounts.csv and signals.csv.")
    p.add_argument("files", nargs="*", help="JSON files in data/staging/ (default: all but EXAMPLE.json)")
    p.add_argument("--asof", help="as-of date, YYYY-MM-DD (default: today); later signal dates are rejected")
    p.add_argument("--dry-run", action="store_true", help="validate and report, write nothing")
    p.add_argument("--quiet", action="store_true", help="only REJECTED lines and the summary")
    p.add_argument("--no-log", action="store_true", help="do not append to data/runs.log")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    today = date.today()
    try:
        asof = parse_date(args.asof) if args.asof else today
    except ValueError:
        sys.exit(f"ingest.py: --asof must be YYYY-MM-DD, got {args.asof!r}")
    run_date = today.isoformat()
    rep = Report(args.quiet)

    files = resolve_inputs(args.files)
    loaded = [(p, load_json(p)) for p in files]  # all parse before anything is written

    suppress = load_suppress(SUPPRESS)
    accounts = read_table(ACCOUNTS, ACCOUNT_HEADERS)
    signals = read_table(SIGNALS, SIGNAL_HEADERS)

    validated = []
    for path, records in loaded:
        for i, raw in enumerate(records, start=1):
            got = validate_account(raw, f"{path.name}#{i}", suppress, asof, run_date, rep)
            if got is not None:
                validated.append(got)

    counts = merge(accounts, signals, validated, run_date, rep)
    counts["records_rejected"] = rep.records_rejected
    changed = (counts["accounts_added"] or counts["accounts_updated"]
               or counts["signals_added"])

    if not args.dry_run and changed:
        # both temps written before either replace, so a crash mid-write
        # never leaves one CSV updated and the other not started
        tmp_a = write_table(accounts, ACCOUNT_HEADERS, ACCOUNTS)
        tmp_s = write_table(signals, SIGNAL_HEADERS, SIGNALS)
        os.replace(tmp_a, ACCOUNTS)
        os.replace(tmp_s, SIGNALS)

    if not args.dry_run and not args.no_log:
        append_log(asof, files, counts)

    print_summary(counts, rep, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
