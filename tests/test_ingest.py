"""Self-check for scripts/ingest.py.

Runs entirely in a temporary directory: the module's paths are pointed at a
throwaway copy, so data/accounts.csv and data/signals.csv are never touched.
Prints PASS or FAIL per case and exits 1 if any case fails.

    python tests/test_ingest.py
"""
import contextlib
import csv
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ingest  # noqa: E402
import score  # noqa: E402
from common import (ACCOUNT_HEADERS, SIGNAL_HEADERS, account_id,  # noqa: E402
                    is_suppressed, load_suppress, signal_id)

ASOF = "2026-11-20"
FAILS = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        FAILS.append(name)


def account(**kw):
    a = {
        "company": "Acme", "website": "https://www.acme.example/", "country": "IN",
        "icp": "commerce", "icp_confidence": "high", "employees": 80, "stage": "series_a",
        "why_live_data": "Tracks SKUs on Blinkit.", "decision_maker": "", "dm_title": "",
        "dm_source": "", "source_url": "https://acme.example/careers", "notes": "",
        "signals": [signal()],
    }
    a.update(kw)
    return a


def signal(**kw):
    s = {"signal_type": "hiring", "signal_date": "2026-10-01",
         "evidence_url": "https://boards-api.greenhouse.io/v1/boards/acme/jobs/1",
         "evidence_note": "Data engineer, scraping.", "date_confidence": "exact"}
    s.update(kw)
    return s


class Sandbox:
    """Points ingest at a temp tree with empty CSVs and the real suppress list."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "data" / "staging").mkdir(parents=True)
        (root / "config").mkdir()
        real_suppress = Path(ingest.SUPPRESS).read_text(encoding="utf-8-sig")
        (root / "config" / "suppress.csv").write_text(real_suppress, encoding="utf-8")
        for name, headers in (("accounts.csv", ACCOUNT_HEADERS), ("signals.csv", SIGNAL_HEADERS)):
            with (root / "data" / name).open("w", encoding="utf-8", newline="") as f:
                csv.writer(f).writerow(headers)
        self.saved = {k: getattr(ingest, k) for k in ("STAGING", "ACCOUNTS", "SIGNALS", "SUPPRESS", "RUNS_LOG")}
        ingest.STAGING = root / "data" / "staging"
        ingest.ACCOUNTS = root / "data" / "accounts.csv"
        ingest.SIGNALS = root / "data" / "signals.csv"
        ingest.SUPPRESS = root / "config" / "suppress.csv"
        ingest.RUNS_LOG = root / "data" / "runs.log"
        self.root = root
        return self

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            setattr(ingest, k, v)
        self.tmp.cleanup()

    def stage(self, name, records):
        p = ingest.STAGING / name
        p.write_text(json.dumps(records), encoding="utf-8")
        return str(p)

    def run(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ingest.main(list(args) + ["--asof", ASOF])
        return buf.getvalue()

    def rows(self, path):
        with path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def bytes(self):
        return ingest.ACCOUNTS.read_bytes(), ingest.SIGNALS.read_bytes()


def rejection_cases():
    cases = [
        ("missing website", account(website=""), "field=website  is missing"),
        ("empty domain", account(website="https://"), "normalises to an empty domain"),
        ("suppressed", account(website="https://www.brightdata.com"), "suppressed: brightdata.com (competitor)"),
        ("suppressed subdomain", account(website="https://jobs.openai.com"), "suppressed: openai.com"),
        ("bad icp", account(icp="fintech"), "field=icp"),
        ("stage not in STAGES", account(stage="pre_series_a"),
         "field=stage  'pre_series_a' is not one of seed, series_a"),
        ("dm without source", account(decision_maker="Jane Doe"), "field=dm_source"),
        ("no evidence_url", account(signals=[signal(evidence_url="")]), "field=evidence_url  is missing"),
        ("non-http url", account(signals=[signal(evidence_url="ftp://x")]), "does not start with http"),
        ("no signal_date", account(signals=[signal(signal_date="")]), "signal_date is missing"),
        ("non-ISO date", account(signals=[signal(signal_date="01/10/2026")]), "not an ISO date"),
        ("trailing junk date", account(signals=[signal(signal_date="2026-10-01 approx")]), "not an ISO date"),
        ("future date", account(signals=[signal(signal_date="2026-11-21")]), "after --asof"),
        ("bad signal_type", account(signals=[signal(signal_type="press")]), "field=signal_type"),
        ("no signals key", {k: v for k, v in account().items() if k != "signals"}, "field=signals  is missing"),
    ]
    for name, rec, expect in cases:
        with Sandbox() as sb:
            out = sb.run(sb.stage("t.json", [rec]))
            check(f"reject: {name}", expect in out and "REJECTED" in out, out)
            check(f"reject writes nothing: {name}", sb.rows(ingest.ACCOUNTS) == [])

    with Sandbox() as sb:
        out = sb.run(sb.stage("t.json", [account(stage="")]))
        check("empty stage is allowed (not found)", "REJECTED" not in out and "accounts added       1" in out, out)

    with Sandbox() as sb:
        out = sb.run(sb.stage("t.json", [account(signals=[signal(signal_date=""), signal(evidence_url="")])]))
        check("all signals bad rejects account",
              "no valid signal survived (2 given)" in out and "records rejected     3" in out, out)

    with Sandbox() as sb:
        out = sb.run(sb.stage("t.json", [account(icp="x", website="")]))
        check("two reasons, one record counted",
              out.count("REJECTED") == 2 and "records rejected     1" in out, out)


def id_and_stamp_cases():
    with Sandbox() as sb:
        rec = account(account_id="ac_fake", first_seen="2020-01-01",
                      signals=[signal(signal_id="sg_fake", captured_at="")])
        out = sb.run(sb.stage("t.json", [rec]))
        a = sb.rows(ingest.ACCOUNTS)[0]
        s = sb.rows(ingest.SIGNALS)[0]
        check("supplied ids reported", "account_id supplied" in out and "signal_id supplied" in out, out)
        check("account_id derived", a["account_id"] == account_id("acme.example"), a["account_id"])
        check("signal_id derived", s["signal_id"] != "sg_fake" and s["signal_id"].startswith("sg_"))
        today = ingest.date.today().isoformat()
        check("first_seen is run date", a["first_seen"] == today, a["first_seen"])
        check("captured_at defaults to run date", s["captured_at"] == today, s["captured_at"])

    with Sandbox() as sb:
        sb.run(sb.stage("t.json", [account(signals=[signal(captured_at="2026-10-05")])]))
        check("captured_at kept when given", sb.rows(ingest.SIGNALS)[0]["captured_at"] == "2026-10-05")


def idempotency_cases():
    with Sandbox() as sb:
        f = sb.stage("t.json", [account(), account(company="Beta", website="beta.example")])
        out1 = sb.run(f)
        first = sb.bytes()
        out2 = sb.run(f)
        check("second run byte-identical", sb.bytes() == first)
        check("first run counts", "accounts added       2" in out1 and "signals added        2" in out1, out1)
        check("second run counts",
              "accounts added       0" in out2 and "accounts updated     0" in out2
              and "signals added        0" in out2 and "signals duplicate    2" in out2, out2)
        log = ingest.RUNS_LOG.read_text(encoding="utf-8").splitlines()
        check("one log line per run", len(log) == 2 and "files=t.json" in log[0], log)

    with Sandbox() as sb:
        sb.run(sb.stage("a.json", [account()]))
        a0 = sb.rows(ingest.ACCOUNTS)[0]
        # same domain written differently, new note, new signal, empty country
        upd = account(website="http://acme.example", notes="Raised Series A.", country="",
                      signals=[signal(signal_type="funding", evidence_url="https://news.example/acme")])
        out = sb.run(sb.stage("b.json", [upd]))
        rows = sb.rows(ingest.ACCOUNTS)
        check("update in place, no duplicate", len(rows) == 1, rows)
        check("updated count", "accounts updated     1" in out, out)
        check("non-empty field updates", rows[0]["notes"] == "Raised Series A.")
        check("empty field never blanks", rows[0]["country"] == "IN", rows[0]["country"])
        check("first_seen never overwritten", rows[0]["first_seen"] == a0["first_seen"])
        check("new signal appended", len(sb.rows(ingest.SIGNALS)) == 2)

    with Sandbox() as sb:
        f = sb.stage("t.json", [account(signals=[signal(), signal(evidence_url="HTTPS://BOARDS-API.GREENHOUSE.IO/v1/boards/acme/jobs/1")])])
        out = sb.run(f)
        check("same signal twice in one file is one row",
              len(sb.rows(ingest.SIGNALS)) == 1 and "signals duplicate    1" in out, out)

    with Sandbox() as sb:
        sb.run(sb.stage("a.json", [account(decision_maker="Jane Doe", dm_title="CTO",
                                           dm_source="https://acme.example/team")]))
        sb.run(sb.stage("b.json", [account(dm_title="VP Data")]))
        r = sb.rows(ingest.ACCOUNTS)[0]
        check("bare title does not overwrite a named DM's title",
              (r["decision_maker"], r["dm_title"]) == ("Jane Doe", "CTO"), r)

    # Mutable signal fields: date_confidence and evidence_note only.
    with Sandbox() as sb:
        sb.run(sb.stage("a.json", [account(signals=[signal(date_confidence="approx")])]))
        out = sb.run(sb.stage("b.json", [account(signals=[signal(date_confidence="ceiling")])]))
        rows = sb.rows(ingest.SIGNALS)
        check("changed date_confidence updates in place",
              len(rows) == 1 and rows[0]["date_confidence"] == "ceiling", rows)
        check("signals updated counted",
              "signals updated      1" in out and "signals duplicate    0" in out, out)

        after = sb.bytes()
        out2 = sb.run(sb.stage("b.json", [account(signals=[signal(date_confidence="ceiling")])]))
        check("unchanged re-run updates nothing",
              "signals updated      0" in out2 and "signals duplicate    1" in out2, out2)
        check("unchanged re-run is byte-identical", sb.bytes() == after)

    with Sandbox() as sb:
        sb.run(sb.stage("a.json", [account(signals=[signal()])]))
        before = sb.bytes()
        out = sb.run(sb.stage("b.json", [account(signals=[signal(signal_date="2026-09-01")])]))
        rows = sb.rows(ingest.SIGNALS)
        check("signal_date change on existing id is ignored",
              len(rows) == 1 and rows[0]["signal_date"] == "2026-10-01", rows)
        check("ignored signal_date change counts nothing and writes nothing",
              "signals updated      0" in out and sb.bytes() == before, out)

    with Sandbox() as sb:
        f = sb.stage("t.json", [account()])
        before = sb.bytes()
        out = sb.run(f, "--dry-run")
        check("dry run writes nothing", sb.bytes() == before and not ingest.RUNS_LOG.exists())
        check("dry run still reports", "accounts added       1" in out and "dry run" in out, out)


def suppression_cases():
    """Pins the shared rule: jobs.openai.com is suppressed by the openai.com
    entry, and ingest.py and score.py agree because both call common.py."""
    table = load_suppress()
    check("jobs.openai.com suppressed by openai.com",
          is_suppressed("jobs.openai.com", table) == ("openai.com", table["openai.com"]),
          is_suppressed("jobs.openai.com", table))
    check("lookalike not suppressed", is_suppressed("notopenai.com", table) is None)
    acct = {"website": "https://jobs.openai.com", "icp_confidence": "high", "stage": "series_b"}
    tier, reason = score.tier_for(acct, table, 90.0, 30.0, 10)
    check("score.py rejects the same subdomain",
          tier == "reject" and "via the openai.com entry" in reason, reason)


def source_ref_cases():
    """source_ref splits signals that share one evidence_url, and leaves every
    id without it exactly as it was before the field existed."""
    acct, url = "ac_6192333d22", "https://api.ashbyhq.com/posting-api/job-board/alt"
    a = signal_id(acct, "hiring", url, "a4be912d-a166-4373-ac52-fdead5ffc463")
    b = signal_id(acct, "hiring", url, "67faa0cc-173a-4788-a9a8-255b836e424d")
    check("same account, type, url; different source_ref -> different ids", a != b, (a, b))
    # sg_fee53baf18 is the id the pre-change signal_id wrote to signals.csv
    # for Alt's first signal; it must not move.
    check("no source_ref -> id unchanged from before the field",
          signal_id(acct, "hiring", url) == "sg_fee53baf18"
          and signal_id(acct, "hiring", url, "") == "sg_fee53baf18"
          and signal_id(acct, "hiring", url, "  ") == "sg_fee53baf18",
          signal_id(acct, "hiring", url))
    check("source_ref ids differ from the no-ref id",
          "sg_fee53baf18" not in (a, b), (a, b))

    board = "https://api.ashbyhq.com/posting-api/job-board/acme"
    with Sandbox() as sb:
        f = sb.stage("t.json", [account(signals=[
            signal(evidence_url=board, source_ref="job-1"),
            signal(evidence_url=board, source_ref="job-2", signal_date="2026-10-05")])])
        out = sb.run(f)
        sgs = sb.rows(ingest.SIGNALS)
        check("ingest keeps both postings on one board",
              len(sgs) == 2 and len({s["signal_id"] for s in sgs}) == 2
              and [s["source_ref"] for s in sgs] == ["job-1", "job-2"], out)

    with Sandbox() as sb:
        f = sb.stage("t.json", [account(signals=[signal(source_ref="has space")])])
        out = sb.run(f)
        check("bad source_ref rejected", "field=source_ref" in out
              and len(sb.rows(ingest.SIGNALS)) == 0, out)

    with Sandbox() as sb:
        f = sb.stage("t.json", [account(signals=[signal(evidence_url=board),
                                                 signal(evidence_url=board + "#job-2")])])
        sb.run(f)
        old_sid = sb.rows(ingest.SIGNALS)[1]["signal_id"]
        f = sb.stage("t.json", [account(signals=[signal(evidence_url=board),
                                                 signal(evidence_url=board, source_ref="job-2")])])
        out = sb.run(f)
        sgs = sb.rows(ingest.SIGNALS)
        check("fragment row migrated in place",
              len(sgs) == 2 and sgs[1]["evidence_url"] == board and sgs[1]["source_ref"] == "job-2"
              and sgs[1]["signal_id"] != old_sid and sgs[1]["signal_id"] != sgs[0]["signal_id"]
              and "signals migrated     1" in out and f"{old_sid} -> " in out, out)
        before = sb.bytes()
        out = sb.run(f)
        check("migration is idempotent", sb.bytes() == before
              and "signals migrated     0" in out and "signals duplicate    2" in out, out)

    with Sandbox() as sb:
        legacy = [h for h in SIGNAL_HEADERS if h != "source_ref"]
        sid = signal_id(account_id("https://acme.example"), "hiring", board)
        with ingest.SIGNALS.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(legacy)
            w.writerow([sid, account_id("https://acme.example"), "hiring", "2026-10-01",
                        "2026-11-01", board, "note", "exact"])
        f = sb.stage("t.json", [account(signals=[signal(evidence_url=board)])])
        out = sb.run(f)
        sgs = sb.rows(ingest.SIGNALS)
        with ingest.SIGNALS.open(encoding="utf-8") as fh:
            header = fh.readline().strip().split(",")
        check("legacy header upgraded, stored id kept",
              header == SIGNAL_HEADERS and len(sgs) == 1 and sgs[0]["signal_id"] == sid
              and sgs[0]["source_ref"] == "" and "UPGRADED" in out, out)


def main():
    source_ref_cases()
    suppression_cases()
    rejection_cases()
    id_and_stamp_cases()
    idempotency_cases()
    print(f"\n{'FAILED ' + str(len(FAILS)) if FAILS else 'ALL PASSED'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
