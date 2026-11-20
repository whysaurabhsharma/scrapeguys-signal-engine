"""Find likely duplicate accounts that ingest.py cannot catch.

ingest.py keys an account on account_id, derived from the normalised domain,
so the same company under two domains becomes two rows. This script finds
those pairs. Standard library only. Name and domain normalisation come from
common.py; nothing about the contract is decided here.

A pair is reported when any of these rules match:
  name       normalise_name is identical (and not empty)
  substring  one normalised name contains the other, both 4+ characters
  tld        the domains differ only by public suffix (alt.xyz vs alt.com)
  redirect   one row's notes say "redirects_to <url or domain>" and that
             domain is the other row's domain

REPORT ONLY by default. Nothing is written unless --apply is given.

With --apply, pairs are grouped into clusters (A~B and B~C is one cluster).
In each cluster the row with the most non-empty fields is kept; a tie keeps
the row that appears first in accounts.csv. Every other row is removed and
its signals are moved to the kept account_id. A moved signal gets its
signal_id re-derived from the kept account_id, because signal_id is a hash
of the account; one that then collides with a signal already on the kept
account is dropped as a duplicate. Both CSVs are written via temp file and
replace. scored.csv is not touched: re-run score.py afterwards.

    python scripts/dedupe.py [--apply] [--quiet] [--no-log]
"""
import argparse
import csv
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    ACCOUNT_HEADERS,
    SIGNAL_HEADERS,
    normalise_domain,
    normalise_name,
    signal_id,
)

ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS = ROOT / "data" / "accounts.csv"
SIGNALS = ROOT / "data" / "signals.csv"
RUNS_LOG = ROOT / "data" / "runs.log"

MIN_SUBSTRING = 4

# Two-label public suffixes seen in this market. Without these, alt.co.in
# would be read as label "co" and never match alt.com.
MULTI_SUFFIXES = {
    "co.in", "net.in", "org.in", "firm.in", "gen.in", "ind.in",
    "co.uk", "org.uk", "com.au", "net.au", "co.nz", "com.sg", "com.br",
    "co.jp", "com.cn", "com.hk", "co.za", "com.mx", "co.id", "com.my",
}

REDIRECT = re.compile(r"redirects_to\s*[:=]?\s*([^\s,;|]+)", re.IGNORECASE)

RULE_ORDER = ("name", "substring", "tld", "redirect")


# ---------------------------------------------------------------- rules

def split_suffix(domain: str):
    """(everything before the public suffix, suffix). ('', '') if no dot."""
    parts = domain.split(".")
    if len(parts) < 2:
        return "", ""
    if len(parts) >= 3 and ".".join(parts[-2:]) in MULTI_SUFFIXES:
        return ".".join(parts[:-2]), ".".join(parts[-2:])
    return ".".join(parts[:-1]), parts[-1]


def redirect_target(notes: str) -> str:
    """Normalised domain from a 'redirects_to X' note, or ''."""
    m = REDIRECT.search(notes or "")
    return normalise_domain(m.group(1)) if m else ""


def filled(row: dict) -> int:
    """Number of non-empty account fields."""
    return sum(1 for h in ACCOUNT_HEADERS if (row.get(h) or "").strip())


def match_rules(a: dict, b: dict) -> list:
    """Every rule that matches this pair, in RULE_ORDER."""
    rules = []
    na, nb = normalise_name(a.get("company")), normalise_name(b.get("company"))
    da, db = normalise_domain(a.get("website")), normalise_domain(b.get("website"))

    if na and na == nb:
        rules.append("name")
    elif (len(na) >= MIN_SUBSTRING and len(nb) >= MIN_SUBSTRING
          and (na in nb or nb in na)):
        rules.append("substring")

    if da and db and da != db:
        sa, sb = split_suffix(da), split_suffix(db)
        if sa[0] and sa[0] == sb[0] and sa[1] != sb[1]:
            rules.append("tld")

    ra, rb = redirect_target(a.get("notes")), redirect_target(b.get("notes"))
    if (ra and ra == db) or (rb and rb == da):
        rules.append("redirect")

    return rules


def find_pairs(accounts: list) -> list:
    """[(i, j, rules)] with i < j as row indexes into accounts."""
    pairs = []
    for i in range(len(accounts)):
        for j in range(i + 1, len(accounts)):
            if accounts[i]["account_id"] == accounts[j]["account_id"]:
                continue  # same domain; ingest.py's job, not this one
            rules = match_rules(accounts[i], accounts[j])
            if rules:
                pairs.append((i, j, rules))
    return pairs


def keeper(accounts: list, idxs) -> int:
    """Most non-empty fields wins; a tie goes to the earliest row."""
    return min(idxs, key=lambda k: (-filled(accounts[k]), k))


# ---------------------------------------------------------------- apply

def clusters(n: int, pairs: list) -> list:
    """Connected components of size 2+, each a sorted list of row indexes."""
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j, _ in pairs:
        parent[find(i)] = find(j)
    groups = {}
    for k in range(n):
        groups.setdefault(find(k), []).append(k)
    return sorted((sorted(g) for g in groups.values() if len(g) > 1), key=lambda g: g[0])


def plan_merges(accounts: list, signals: list, pairs: list):
    """Pure. Returns (new_accounts, new_signals, merges) without writing.

    merges is a list of dicts describing each removed row, for printing.
    """
    drop = {}  # removed row index -> kept row index
    for group in clusters(len(accounts), pairs):
        k = keeper(accounts, group)
        for g in group:
            if g != k:
                drop[g] = k

    remap = {accounts[g]["account_id"]: accounts[k]["account_id"] for g, k in drop.items()}
    new_accounts = [r for i, r in enumerate(accounts) if i not in drop]

    kept_sids = {s["signal_id"] for s in signals if s["account_id"] not in remap}
    new_signals, moved, dupes = [], {}, {}
    for s in signals:
        old = s["account_id"]
        if old not in remap:
            new_signals.append(s)
            continue
        target = remap[old]
        row = dict(s)
        row["account_id"] = target
        row["signal_id"] = signal_id(target, row["signal_type"], row["evidence_url"])
        if row["signal_id"] in kept_sids:
            dupes.setdefault(old, []).append((s["signal_id"], row["signal_id"]))
            continue
        kept_sids.add(row["signal_id"])
        new_signals.append(row)
        moved.setdefault(old, []).append((s["signal_id"], row["signal_id"]))

    merges = []
    for g, k in sorted(drop.items(), key=lambda x: (x[1], x[0])):
        gone, kept = accounts[g], accounts[k]
        lost = [h for h in ACCOUNT_HEADERS
                if h != "account_id" and (gone.get(h) or "").strip()
                and not (kept.get(h) or "").strip()]
        merges.append({
            "removed": gone, "kept": kept,
            "moved": moved.get(gone["account_id"], []),
            "duplicates": dupes.get(gone["account_id"], []),
            "lost_fields": lost,
        })
    return new_accounts, new_signals, merges


# ---------------------------------------------------------------- io

def read_table(path: Path, headers: list) -> list:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []
        if list(reader.fieldnames) != list(headers):
            sys.exit(f"dedupe.py: {path.name} header does not match common.py.\n"
                     f"  found:    {','.join(reader.fieldnames)}\n"
                     f"  expected: {','.join(headers)}")
        return [dict(r) for r in reader]


def write_table(rows: list, headers: list, out: Path) -> Path:
    tmp = out.with_suffix(out.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)
    return tmp


def append_log(mode: str, counts: dict) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    parts = "\t".join(f"{k}={v}" for k, v in counts.items())
    with RUNS_LOG.open("a", encoding="utf-8", newline="") as f:
        f.write(f"{stamp}\tdedupe.py\tmode={mode}\t{parts}\n")


# ---------------------------------------------------------------- output

def print_pair(a: dict, b: dict, rules: list) -> None:
    fa, fb = filled(a), filled(b)
    richer = (a["account_id"] if fa > fb else b["account_id"] if fb > fa
              else f"tie, keep first ({a['account_id']})")
    print(f"PAIR      rules={','.join(rules)}")
    print(f"  A  {a['account_id']}  {a['company']}  {a['website']}  fields={fa}")
    print(f"  B  {b['account_id']}  {b['company']}  {b['website']}  fields={fb}")
    print(f"  more fields: {richer}")


def print_merge(m: dict) -> None:
    gone, kept = m["removed"], m["kept"]
    print(f"MERGED    {gone['account_id']} ({gone['company']}, {gone['website']})"
          f"  ->  {kept['account_id']} ({kept['company']}, {kept['website']})")
    for old, new in m["moved"]:
        print(f"  signal moved      {old} -> {new}")
    for old, new in m["duplicates"]:
        print(f"  signal dropped    {old} (already on kept account as {new})")
    for h in m["lost_fields"]:
        print(f"  field not kept    {h}={m['removed'][h]!r}")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Report suspected duplicate accounts. Writes nothing without --apply.")
    p.add_argument("--apply", action="store_true", help="merge the reported pairs into the richer row")
    p.add_argument("--quiet", action="store_true", help="summary only (merges still print with --apply)")
    p.add_argument("--no-log", action="store_true", help="do not append to data/runs.log")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    accounts = read_table(ACCOUNTS, ACCOUNT_HEADERS)
    signals = read_table(SIGNALS, SIGNAL_HEADERS)
    pairs = find_pairs(accounts)

    if not args.quiet:
        for i, j, rules in pairs:
            print_pair(accounts[i], accounts[j], rules)

    counts = {"accounts": len(accounts), "pairs": len(pairs)}
    for r in RULE_ORDER:
        counts[f"rule_{r}"] = sum(1 for *_, rules in pairs if r in rules)

    if args.apply and pairs:
        new_accounts, new_signals, merges = plan_merges(accounts, signals, pairs)
        tmp_a = write_table(new_accounts, ACCOUNT_HEADERS, ACCOUNTS)
        tmp_s = write_table(new_signals, SIGNAL_HEADERS, SIGNALS)
        os.replace(tmp_a, ACCOUNTS)
        os.replace(tmp_s, SIGNALS)
        for m in merges:
            print_merge(m)
        counts["merged"] = len(merges)
        counts["signals_moved"] = sum(len(m["moved"]) for m in merges)
        counts["signals_dropped"] = sum(len(m["duplicates"]) for m in merges)
        print("scored.csv is now stale: run python scripts/score.py")
    else:
        counts["merged"] = 0

    if not args.no_log:
        append_log("apply" if args.apply else "report", counts)

    print("Summary:" if args.apply else "Summary (report only, nothing written):")
    for k, v in counts.items():
        print(f"  {k:<18} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
