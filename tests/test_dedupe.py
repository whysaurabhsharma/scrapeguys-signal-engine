"""Self-check for scripts/dedupe.py.

Rule cases build rows in memory. The write cases point the module's paths at a
temporary directory, so nothing under data/ is ever read or written.
Prints PASS or FAIL per case and exits 1 if any case fails.

    python tests/test_dedupe.py
"""
import contextlib
import csv
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dedupe  # noqa: E402
from common import ACCOUNT_HEADERS, SIGNAL_HEADERS, account_id, signal_id  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        FAILS.append(name)


def row(company, website, **kw):
    r = {h: "" for h in ACCOUNT_HEADERS}
    r.update(company=company, website=website, icp="commerce", account_id=account_id(website))
    r.update(kw)
    return r


def sig(acct_row, url, **kw):
    s = {h: "" for h in SIGNAL_HEADERS}
    s.update(account_id=acct_row["account_id"], signal_type="hiring",
             signal_date="2026-10-01", captured_at="2026-11-01",
             evidence_url=url, date_confidence="exact")
    s["signal_id"] = signal_id(s["account_id"], "hiring", url)
    s.update(kw)
    return s


def rules_for(a, b):
    pairs = dedupe.find_pairs([a, b])
    return pairs[0][2] if pairs else []


# ---------------------------------------------------------------- rules

def rule_cases():
    got = rules_for(row("Acme Technologies Pvt Ltd", "https://acme.in"),
                    row("Acme Inc", "https://www.acmeretail.com/"))
    check("exact name under two domains", got == ["name"], got)

    got = rules_for(row("Alt", "https://alt.xyz"),
                    row("Alternate Mobility", "https://alt.com"))
    check("TLD-only difference", got == ["tld"], got)

    got = rules_for(row("Alt", "https://alt.co.in"), row("Other", "https://alt.com"))
    check("TLD-only difference, two-label suffix", got == ["tld"], got)

    got = rules_for(row("Zepto", "https://zepto.com"),
                    row("Zepto Now", "https://zeptonow.com"))
    check("substring fires, both 4+ chars", got == ["substring"], got)

    got = rules_for(row("Zep", "https://zep.ai"),
                    row("Zepto", "https://zepto.com"))
    check("substring does not fire, one name under 4", got == [], got)

    # guards against the obvious false positives
    got = rules_for(row("India Pvt Ltd", "https://a.example"),
                    row("Technologies Ltd", "https://b.example"))
    check("names that normalise to empty never match", got == [], got)

    got = rules_for(row("Shop", "https://shop.app.com"), row("Mart", "https://app.io"))
    check("subdomain is not a TLD-only difference", got == [], got)

    got = rules_for(row("Foo", "https://foo.example", notes="redirects_to https://www.bar.example/"),
                    row("Bar", "https://bar.example"))
    check("redirect note", got == ["redirect"], got)


# ---------------------------------------------------------------- writes

class Sandbox:
    def __init__(self, accounts, signals):
        self.accounts, self.signals = accounts, signals

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.saved = {k: getattr(dedupe, k) for k in ("ACCOUNTS", "SIGNALS", "RUNS_LOG")}
        dedupe.ACCOUNTS = root / "accounts.csv"
        dedupe.SIGNALS = root / "signals.csv"
        dedupe.RUNS_LOG = root / "runs.log"
        for path, headers, rows in ((dedupe.ACCOUNTS, ACCOUNT_HEADERS, self.accounts),
                                    (dedupe.SIGNALS, SIGNAL_HEADERS, self.signals)):
            with path.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=headers)
                w.writeheader()
                w.writerows(rows)
        return self

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            setattr(dedupe, k, v)
        self.tmp.cleanup()

    def run(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            dedupe.main(list(args) + ["--no-log"])
        return buf.getvalue()

    def rows(self, path):
        with path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))


def write_cases():
    rich = row("Acme", "https://acme.in", country="IN", stage="series_a", notes="x")
    thin = row("Acme Inc", "https://acme.com")
    other = row("Unrelated", "https://unrelated.example")
    shared_url = "https://boards-api.greenhouse.io/v1/boards/acme/jobs/1"
    sigs = [sig(rich, shared_url), sig(thin, shared_url),
            sig(thin, "https://boards-api.greenhouse.io/v1/boards/acme/jobs/2"),
            sig(other, "https://example.com/job")]

    with Sandbox([thin, rich, other], sigs) as sb:
        before = dedupe.ACCOUNTS.read_bytes(), dedupe.SIGNALS.read_bytes()
        out = sb.run()
        after = dedupe.ACCOUNTS.read_bytes(), dedupe.SIGNALS.read_bytes()
        check("report only writes nothing", before == after)
        check("report names the richer row", f"more fields: {rich['account_id']}" in out, out)

    with Sandbox([thin, rich, other], sigs) as sb:
        out = sb.run("--apply")
        accts = sb.rows(dedupe.ACCOUNTS)
        sgs = sb.rows(dedupe.SIGNALS)
        ids = [a["account_id"] for a in accts]
        check("apply keeps the richer row", ids == [rich["account_id"], other["account_id"]], ids)
        check("apply moves signals to the kept id",
              all(s["account_id"] != thin["account_id"] for s in sgs), sgs)
        check("apply drops the colliding signal, keeps the new one", len(sgs) == 3, len(sgs))
        check("moved signal_id is re-derived",
              all(s["signal_id"] == signal_id(s["account_id"], s["signal_type"], s["evidence_url"],
                                              s["source_ref"])
                  for s in sgs))
        check("apply prints the merge",
              f"MERGED    {thin['account_id']}" in out and "signal dropped" in out, out)


def main():
    rule_cases()
    write_cases()
    print(f"\n{'FAILED ' + str(len(FAILS)) if FAILS else 'ALL PASSED'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
