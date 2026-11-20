"""Acceptance checks for the repo. Standard library only.

Two groups of checks.

CORE (C1-C10, G): PASS, FAIL, WARN or NOT YET BUILT. A CORE failure means
the machine is broken. Exits 1 if any CORE check FAILs.

TARGET (T1-T9): PASS or MISS, always with the actual number. A TARGET miss
means there is not yet enough output, not that anything is broken. It does
not change the exit code unless --strict is given. T9 alone can also report
NOT RUN HERE: data/runs.log is gitignored, so a fresh clone has no run
history. NOT RUN HERE is never counted as a pass.

Verdict: NOT WORKING if any CORE fails, WORKING if all CORE and TARGET
checks pass, CORRECT BUT THIN otherwise.

Never modifies data/. Anything that writes (ingest, score) runs inside a
temporary copy of scripts/, config/ and data/, so ROOT in those scripts
resolves to the copy. data/ is hashed before and after the run and the
result is reported as a final guard check.

    python scripts/acceptance.py [--asof YYYY-MM-DD] [--quiet] [--json]
                                 [--strict] [--sample N]
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    ACCOUNT_HEADERS,
    ROOT,
    SCORED_HEADERS,
    SIGNAL_HEADERS,
    is_suppressed,
    load_suppress,
    normalise_domain,
    parse_date,
)

DATA = ROOT / "data"
TABLES = {
    "accounts.csv": ACCOUNT_HEADERS,
    "signals.csv": SIGNAL_HEADERS,
    "scored.csv": SCORED_HEADERS,
}
PY = sys.executable or "python"
SUBPROCESS_TIMEOUT = 300

PASS, FAIL, WARN, NYB, MISS = "PASS", "FAIL", "WARN", "NOT YET BUILT", "MISS"
NRH = "NOT RUN HERE"


class Result:
    def __init__(self, cid, name, status, reason, details=None):
        self.cid, self.name, self.status, self.reason = cid, name, status, reason
        self.details = details or []

    def as_dict(self):
        return {"id": self.cid, "name": self.name, "status": self.status,
                "reason": self.reason, "details": self.details}


# ---------------------------------------------------------------- helpers

def read_rows(path: Path):
    """(header, rows as dicts). Missing file gives (None, [])."""
    if not path.exists():
        return None, []
    with path.open(encoding="utf-8-sig", newline="") as f:
        # Rows whose first cell starts with "#" are comments (golden.csv uses one).
        reader = (r for r in csv.reader(f) if not (r and r[0].lstrip().startswith("#")))
        header = next(reader, [])
        rows = [dict(zip(header, r)) for r in reader if any(c.strip() for c in r)]
    return header, rows


def hash_tree(root: Path) -> dict:
    out = {}
    if root.exists():
        for p in sorted(root.rglob("*")):
            if p.is_file():
                out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def make_sandbox() -> Path:
    """Temp repo copy: scripts/, config/, data/. Caller removes it."""
    tmp = Path(tempfile.mkdtemp(prefix="acceptance_"))
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for sub in ("scripts", "config", "data"):
        src = ROOT / sub
        if src.exists():
            shutil.copytree(src, tmp / sub, ignore=ignore)
    return tmp


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          timeout=SUBPROCESS_TIMEOUT)


def last_line(text: str) -> str:
    lines = [l for l in (text or "").strip().splitlines() if l.strip()]
    return lines[-1].strip() if lines else ""


# ---------------------------------------------------------------- checks

def c1_schema(asof):
    bad = []
    for name, expected in TABLES.items():
        header, _ = read_rows(DATA / name)
        if header is None:
            bad.append(f"{name}: missing")
        elif header != expected:
            bad.append(f"{name}: got {header}, want {expected}")
    if bad:
        return Result("C1", "Schema", FAIL, bad[0], bad)
    return Result("C1", "Schema", PASS, "all three CSV headers match common.py exactly, in order")


def c2_referential(asof):
    _, accounts = read_rows(DATA / "accounts.csv")
    _, signals = read_rows(DATA / "signals.csv")
    _, scored = read_rows(DATA / "scored.csv")
    ids = {a.get("account_id", "") for a in accounts}
    bad = [f"signals.csv {s.get('signal_id', '?')}: account_id {s.get('account_id', '')!r} not in accounts.csv"
           for s in signals if s.get("account_id", "") not in ids]
    bad += [f"scored.csv: account_id {r.get('account_id', '')!r} not in accounts.csv"
            for r in scored if r.get("account_id", "") not in ids]
    if bad:
        return Result("C2", "Referential integrity", FAIL, f"{len(bad)} orphan row(s); first: {bad[0]}", bad)
    return Result("C2", "Referential integrity", PASS,
                  f"{len(signals)} signal and {len(scored)} scored row(s) all resolve to {len(accounts)} account(s)")


def c3_idempotency(asof):
    tmp = make_sandbox()
    try:
        staging = tmp / "data" / "staging"
        files = sorted(staging.glob("*.json"))  # EXAMPLE.json included as a fixture
        if not files:
            return Result("C3", "Idempotency", FAIL, "no JSON in data/staging/ to ingest")
        cmd = [PY, str(tmp / "scripts" / "ingest.py"), *map(str, files),
               "--asof", asof.isoformat(), "--quiet", "--no-log"]
        snaps = []
        for i in (1, 2):
            r = run(cmd, tmp)
            if r.returncode != 0:
                return Result("C3", "Idempotency", FAIL,
                              f"ingest run {i} exited {r.returncode}: {last_line(r.stderr or r.stdout)}")
            snaps.append({n: (tmp / "data" / n).read_bytes() for n in ("accounts.csv", "signals.csv")})
        diff = [n for n in snaps[0] if snaps[0][n] != snaps[1][n]]
        names = ", ".join(f.name for f in files)
        if diff:
            return Result("C3", "Idempotency", FAIL, f"second ingest changed {', '.join(diff)} (inputs: {names})")
        rows = snaps[1]["accounts.csv"].count(b"\n") - 1
        return Result("C3", "Idempotency", PASS,
                      f"second ingest of {names} left both CSVs byte-identical ({rows} account row(s))")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def c4_determinism(asof):
    tmp = make_sandbox()
    try:
        # seed the sandbox with the EXAMPLE fixture so the comparison is not
        # trivially two empty files
        ex = tmp / "data" / "staging" / "EXAMPLE.json"
        note = ""
        if ex.exists():
            r = run([PY, str(tmp / "scripts" / "ingest.py"), str(ex),
                     "--asof", asof.isoformat(), "--quiet", "--no-log"], tmp)
            note = " (data + EXAMPLE fixture)" if r.returncode == 0 else ""
        outs = []
        for i in (1, 2):
            out = tmp / f"scored_{i}.csv"
            r = run([PY, str(tmp / "scripts" / "score.py"), "--asof", asof.isoformat(),
                     "--out", str(out), "--quiet", "--no-log"], tmp)
            if r.returncode != 0:
                return Result("C4", "Determinism", FAIL,
                              f"score run {i} exited {r.returncode}: {last_line(r.stderr or r.stdout)}")
            outs.append(out.read_bytes())
        if outs[0] != outs[1]:
            return Result("C4", "Determinism", FAIL, f"two score runs at --asof {asof} differ")
        rows = outs[0].count(b"\n") - 1
        return Result("C4", "Determinism", PASS,
                      f"two score runs at --asof {asof} byte-identical, {rows} row(s){note}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def c5_provenance(asof):
    _, accounts = read_rows(DATA / "accounts.csv")
    _, signals = read_rows(DATA / "signals.csv")
    bad = [f"signal {s.get('signal_id', '?')}: evidence_url {s.get('evidence_url', '')!r}"
           for s in signals if not s.get("evidence_url", "").strip().lower().startswith("http")]
    bad += [f"account {a.get('account_id', '?')} ({a.get('company', '')}): decision_maker without dm_source"
            for a in accounts if a.get("decision_maker", "").strip() and not a.get("dm_source", "").strip()]
    if bad:
        return Result("C5", "Provenance", FAIL, f"{len(bad)} unsourced item(s); first: {bad[0]}", bad)
    dms = sum(1 for a in accounts if a.get("decision_maker", "").strip())
    return Result("C5", "Provenance", PASS,
                  f"{len(signals)} signal(s) with http evidence_url, {dms} decision maker(s) all sourced")


def c6_dates(asof):
    _, signals = read_rows(DATA / "signals.csv")
    bad, stamped = [], 0
    for s in signals:
        sid, raw = s.get("signal_id", "?"), s.get("signal_date", "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw.strip()):
            bad.append(f"signal {sid}: signal_date {raw!r} is not YYYY-MM-DD")
            continue
        try:
            d = parse_date(raw)
        except ValueError:
            bad.append(f"signal {sid}: signal_date {raw!r} is not a real date")
            continue
        if d > asof:
            bad.append(f"signal {sid}: signal_date {raw} is after --asof {asof}")
        if raw.strip() == s.get("captured_at", "").strip()[:10]:
            stamped += 1
    if bad:
        return Result("C6", "Dates", FAIL, f"{len(bad)} bad date(s); first: {bad[0]}", bad)
    if signals and stamped * 2 > len(signals):
        return Result("C6", "Dates", WARN,
                      f"{stamped}/{len(signals)} signal_date equal captured_at: dates may be stamped, not found")
    return Result("C6", "Dates", PASS,
                  f"{len(signals)} signal_date(s) ISO and <= {asof}; {stamped} equal captured_at")


def c7_suppression(asof):
    _, accounts = read_rows(DATA / "accounts.csv")
    table = load_suppress()
    bad = []
    for a in accounts:
        hit = is_suppressed(a.get("website", ""), table)
        if hit:
            bad.append(f"{a.get('company', '')} ({a.get('website', '')}) matches {hit[0]}: {hit[1]}")
    if bad:
        return Result("C7", "Suppression", FAIL, f"{len(bad)} suppressed account(s); first: {bad[0]}", bad)
    return Result("C7", "Suppression", PASS,
                  f"{len(accounts)} account(s) checked against {len(table)} suppress entries, none match")


def c8_guard(asof):
    path = ROOT / ".claude" / "settings.json"
    try:
        settings = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return Result("C8", "Guard registered", FAIL, ".claude/settings.json missing")
    except json.JSONDecodeError as e:
        return Result("C8", "Guard registered", FAIL, f".claude/settings.json does not parse: {e}")

    deny = (settings.get("permissions") or {}).get("deny") or []
    missing = [n for n in TABLES
               if not any(f"data/{n}" in rule and rule.split("(")[0] in ("Edit", "Write")
                          for rule in deny)]
    if missing:
        return Result("C8", "Guard registered", FAIL, f"no Edit/Write deny rule for data/{', data/'.join(missing)}")

    guard = ROOT / ".claude" / "hooks" / "guard.py"
    if not guard.is_file():
        return Result("C8", "Guard registered", NYB,
                      "deny rules on all three CSVs present; .claude/hooks/guard.py absent (Phase 5)")

    commands = []
    for entry in (settings.get("hooks") or {}).get("PreToolUse") or []:
        for h in entry.get("hooks") or []:
            commands.append(h.get("command", ""))
    if not any("guard.py" in c for c in commands):
        return Result("C8", "Guard registered", FAIL,
                      "guard.py exists but no PreToolUse hook in settings.json points at it")
    return Result("C8", "Guard registered", PASS, "deny rules present, PreToolUse hook runs .claude/hooks/guard.py")


# Built from fragments so this file does not match its own scan.
SEND_PATTERNS = [
    ("smtp" + "lib", re.compile(r"\bsmtp" + r"lib\b", re.I)),
    ("send" + "grid", re.compile(r"\bsend" + r"grid\b", re.I)),
    ("mail" + "gun", re.compile(r"\bmail" + r"gun\b", re.I)),
    ("re" + "send", re.compile(r"\bre" + r"send\b", re.I)),
    ("post" + "mark", re.compile(r"\bpost" + r"mark\b", re.I)),
    ("send-mail call", re.compile(r"\bsend[_-]?" + r"mail\s*\(|\.send_?" + r"message\s*\(", re.I)),
]
SCAN_SUFFIXES = {".py", ".md", ".json", ".txt", ".toml", ".yml", ".yaml", ".cfg", ".ini", ".sh", ".ps1", ".csv", ""}


# C9 scope: files directly in the repo root, plus everything under scripts/
# and .claude/ (guard.py included). It does NOT scan tests/.
# tests/test_guard.py deliberately contains send-library strings as test
# inputs for the guard, which is why tests/ is excluded. If this scope ever
# widens to cover tests/, those strings must be split into fragments the way
# guard.py's patterns are, or C9 will flag them.
def c9_never_send(asof):
    files = [p for p in ROOT.iterdir() if p.is_file()]
    for sub in ("scripts", ".claude"):
        d = ROOT / sub
        if d.exists():
            files += [p for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    files = sorted({p for p in files if p.suffix.lower() in SCAN_SUFFIXES})
    hits = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for label, rx in SEND_PATTERNS:
                if rx.search(line):
                    hits.append(f"{p.relative_to(ROOT).as_posix()}:{n}: {label}")
    scanned = [p.relative_to(ROOT).as_posix() for p in files]
    if hits:
        return Result("C9", "Never-send", FAIL, f"{len(hits)} hit(s); first: {hits[0]}", hits + ["scanned: " + ", ".join(scanned)])
    return Result("C9", "Never-send", PASS, f"0 hits in {len(files)} file(s): {', '.join(scanned)}", scanned)


def c10_tests(asof):
    tests = sorted((ROOT / "tests").glob("test_*.py"))
    if not tests:
        return Result("C10", "Tests", FAIL, "no tests/test_*.py found")
    failed, details = [], []
    for t in tests:
        try:
            r = run([PY, str(t)], ROOT)
            code = r.returncode
            tail = last_line(r.stdout) or last_line(r.stderr)
        except subprocess.TimeoutExpired:
            code, tail = "timeout", f"exceeded {SUBPROCESS_TIMEOUT}s"
        details.append(f"{t.name}: exit {code}: {tail}")
        if code != 0:
            failed.append(t.name)
    if failed:
        return Result("C10", "Tests", FAIL, f"{len(failed)}/{len(tests)} failed: {', '.join(failed)}", details)
    return Result("C10", "Tests", PASS, f"{len(tests)}/{len(tests)} exit 0: {', '.join(t.name for t in tests)}", details)


CHECKS = [c1_schema, c2_referential, c3_idempotency, c4_determinism, c5_provenance,
          c6_dates, c7_suppression, c8_guard, c9_never_send, c10_tests]


# ---------------------------------------------------------------- targets
#
# TARGET checks measure how much output exists, not whether the machine is
# correct. Every reason carries the actual number, so a verdict is never
# read without it.

ICPS = ("ai", "travel", "commerce")
TIER_A, TIER_B = "A", "B"
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _score(row):
    try:
        return float(row.get("score", "") or 0)
    except ValueError:
        return 0.0


def tier_a_rows():
    """Tier A rows from scored.csv, highest score first, ties by account_id."""
    _, scored = read_rows(DATA / "scored.csv")
    rows = [r for r in scored if r.get("tier", "") == TIER_A]
    return sorted(rows, key=lambda r: (-_score(r), r.get("account_id", "")))


def brief_for(acct_id):
    d = ROOT / "out" / "briefs"
    hits = sorted(d.glob(f"{acct_id}-*.md")) if d.exists() else []
    return hits[0] if hits else None


def t1_volume(asof):
    _, scored = read_rows(DATA / "scored.csv")
    n = len(scored)
    return Result("T1", "Volume", PASS if n >= 40 else MISS, f"{n} account(s) scored, target 40")


def t2_icp_coverage(asof):
    _, scored = read_rows(DATA / "scored.csv")
    counts = {i: sum(1 for r in scored if r.get("icp", "") == i) for i in ICPS}
    ok = all(c >= 8 for c in counts.values())
    shown = ", ".join(f"{i} {c}" for i, c in counts.items())
    return Result("T2", "ICP coverage", PASS if ok else MISS, f"{shown}; target 8 each")


def t3_signal_types(asof):
    _, signals = read_rows(DATA / "signals.csv")
    types = sorted({s.get("signal_type", "").strip() for s in signals if s.get("signal_type", "").strip()})
    return Result("T3", "Signal types", PASS if len(types) >= 4 else MISS,
                  f"{len(types)} type(s) in use ({', '.join(types) or 'none'}), target 4")


def t4_tier_a_share(asof):
    _, scored = read_rows(DATA / "scored.csv")
    a = sum(1 for r in scored if r.get("tier", "") == TIER_A)
    pct = 100.0 * a / len(scored) if scored else 0.0
    ok = bool(scored) and 10.0 <= pct <= 40.0
    return Result("T4", "Tier A share", PASS if ok else MISS,
                  f"{a}/{len(scored)} Tier A = {pct:.1f}%, target 10-40%")


def t5_briefs(asof):
    top = tier_a_rows()[:10]
    missing = [f"{r.get('company', '')} ({r.get('account_id', '')})"
               for r in top if not brief_for(r.get("account_id", ""))]
    if not top:
        return Result("T5", "Briefs", MISS, "0 Tier A accounts, so 0 briefs to check")
    reason = f"{len(top) - len(missing)}/{len(top)} of the first ten Tier A have a brief in out/briefs/"
    if missing:
        reason += f"; missing: {', '.join(missing)}"
    return Result("T5", "Briefs", MISS if missing else PASS, reason, missing)


def t6_decision_makers(asof):
    _, accounts = read_rows(DATA / "accounts.csv")
    by_id = {a.get("account_id", ""): a for a in accounts}
    top = tier_a_rows()
    named = [r for r in top
             if by_id.get(r.get("account_id", ""), {}).get("decision_maker", "").strip()
             and by_id.get(r.get("account_id", ""), {}).get("dm_source", "").strip()]
    ok = bool(top) and len(named) * 2 >= len(top)
    return Result("T6", "Decision makers", PASS if ok else MISS,
                  f"{len(named)}/{len(top)} Tier A have a named decision maker with dm_source, target half")


def t7_assets(asof):
    adir = ROOT / "out" / "assets"
    found, misses, details = 0, [], []
    for icp in ICPS:
        files = sorted(adir.glob(f"{icp}-*.md")) if adir.exists() else []
        if not files:
            misses.append(f"{icp}: no asset")
            continue
        f = files[-1]  # latest by dated filename
        head = f.read_text(encoding="utf-8", errors="replace").splitlines()[:3]
        # A date is a header, not a finding: strip ISO dates before looking
        # for a digit, or every dated asset passes on its date line alone.
        if re.search(r"\d", ISO_DATE.sub("", "\n".join(head))):
            found += 1
            details.append(f"{icp}: {f.name} has a number in its first three lines")
        else:
            misses.append(f"{icp}: {f.name} has no number in its first three lines, ISO dates ignored")
    reason = f"{found}/{len(ICPS)} ICP asset(s) carry a number in their first three lines"
    if misses:
        reason += f"; {'; '.join(misses)}"
    return Result("T7", "Assets", PASS if found == len(ICPS) else MISS, reason, details + misses)


T8_MIN_BUYERS = 5  # below this many matched buyers, a T8 PASS is marked THIN


def t8_golden(asof):
    """Golden set: buyers should reach A/B, non-buyers should not.

    Buyers are judged only on scored.csv: a buyer must reach Tier A or B.

    A golden "no" row counts as correctly handled if EITHER it scored
    nurture/reject, OR it has ANY row in data/killlist.csv (suppressed,
    vendor, wrong_buyer, off_icp, no_evidenced_why, no_dated_signal). Every
    one of those is the system correctly declining to pitch it, earlier and
    more cheaply than the scorer would. The original check looked only in
    scored.csv and so could never pass: most golden non-buyers are suppressed
    vendors that never reach scored.csv by design, and the rest are stopped
    by the hunt's disqualify and why_live_data gates before ingest.

    A non-buyer with no kill-list row and no score is unmatched, not a pass:
    nobody hunted it, so nothing declined it.

    Strength is reported, not just the verdict. Fewer than T8_MIN_BUYERS
    matched buyers marks the line THIN: a rate over one row must not read
    like a rate over ten.

    What the buyer half measures (2026-11-20): whether a labelled buyer is
    ranked callable NOW, at --asof. That is stricter than whether it would
    buy, which is what the golden label records. A buyer whose only evidence
    is old decays to nurture without the scorer being wrong. So each buyer
    that scores nurture or reject is re-scored, in a sandbox, at the date of
    its own freshest signal, and the line reports how many of those misses
    are AGED (A/B at that date) versus SCORER (nurture even then). The 80%
    target is unchanged and still judged on the tier at --asof.
    """
    _, golden = read_rows(ROOT / "tests" / "golden.csv")
    _, scored = read_rows(DATA / "scored.csv")
    _, killed = read_rows(DATA / "killlist.csv")
    tier_by_domain = {normalise_domain(r.get("website", "")): r.get("tier", "") for r in scored}
    id_by_domain = {normalise_domain(r.get("website", "")): r.get("account_id", "") for r in scored}
    killed_code = {}
    for k in killed:
        kd = normalise_domain(k.get("domain", ""))
        if kd:
            killed_code[kd] = (k.get("reason_code") or "").strip().lower()  # latest row wins
    buy_total = sum(1 for g in golden if g.get("expected", "") == "buy")
    no_total = len(golden) - buy_total
    buy_hit = buy_n = no_hit = no_n = 0
    no_killed = 0
    details = []
    missed_buyers = []  # (domain, account_id, tier at asof) for buyers below B
    for g in golden:
        d = normalise_domain(g.get("domain", ""))
        tier = tier_by_domain.get(d)
        if tier is None:
            if g.get("expected", "") != "buy" and d in killed_code:
                no_n, no_hit, no_killed = no_n + 1, no_hit + 1, no_killed + 1
                details.append(f"{d}: expected no, declined ({killed_code[d]} in killlist.csv), ok")
            elif g.get("expected", "") == "buy" and d in killed_code:
                details.append(f"{d}: expected buy, declined ({killed_code[d]}), unscored, not counted")
            continue
        good = tier in (TIER_A, TIER_B)
        if g.get("expected", "") == "buy":
            buy_n, buy_hit = buy_n + 1, buy_hit + good
            ok = good
            if not good:
                missed_buyers.append((d, id_by_domain.get(d, ""), tier))
                continue  # detail line written below, with the at-freshest tier
        else:
            no_n, no_hit = no_n + 1, no_hit + (not good)
            ok = not good
        details.append(f"{d}: expected {g.get('expected', '')}, tier {tier}, {'ok' if ok else 'WRONG'}")

    aged, scorer_err = _t8_classify_misses(missed_buyers, details)

    def pct(h, n):
        return f"{h}/{n} = {100.0 * h / n:.0f}%" if n else "0/0 = n/a"

    # A rate over zero matched rows is not a pass.
    passed = buy_n > 0 and no_n > 0 and buy_hit * 5 >= buy_n * 4 and no_hit * 5 >= no_n * 4
    thin = buy_n < T8_MIN_BUYERS
    strength = (f"THIN: only {buy_n} buyer(s) matched, need {T8_MIN_BUYERS}. "
                if thin else "")
    misses = ""
    if missed_buyers:
        misses = (f" (of {len(missed_buyers)} below B: {aged} AGED, A/B at their freshest "
                  f"signal's date; {scorer_err} SCORER, nurture even then)")
    reason = (f"{strength}buyers callable now: matched {buy_n}/{buy_total}, "
              f"in A/B at asof {pct(buy_hit, buy_n)}{misses}; "
              f"non-buyers matched {no_n}/{no_total} ({no_n - no_killed} scored, "
              f"{no_killed} declined in killlist.csv), handled {pct(no_hit, no_n)}; "
              f"target 80% each")
    return Result("T8", "Golden set", PASS if passed else MISS, reason, details)


def _t8_classify_misses(missed, details):
    """Re-score each missed buyer at its freshest signal's date, in a sandbox.

    Returns (aged, scorer). AGED: it reaches A/B at that date, so the miss is
    the signal ageing, not the scorer. SCORER: nurture or reject even on the
    day of its freshest signal. Appends one detail line per buyer.
    """
    if not missed:
        return 0, 0
    _, signals = read_rows(DATA / "signals.csv")
    freshest = {}
    for s in signals:
        d = parse_date(s.get("signal_date", ""))
        aid = s.get("account_id", "")
        if d and (aid not in freshest or d > freshest[aid]):
            freshest[aid] = d
    aged = scorer = 0
    tmp = make_sandbox()
    try:
        for domain, aid, tier_now in missed:
            when = freshest.get(aid)
            if when is None:
                details.append(f"{domain}: expected buy, tier {tier_now} at asof, "
                               f"no dated signal to re-score, WRONG")
                scorer += 1
                continue
            out = tmp / f"t8_{aid}.csv"
            r = run([PY, str(tmp / "scripts" / "score.py"), "--asof", when.isoformat(),
                     "--out", str(out), "--quiet", "--no-log"], tmp)
            _, rows = read_rows(out) if r.returncode == 0 else (None, [])
            then = next((x.get("tier", "") for x in rows if x.get("account_id", "") == aid), "")
            if then in (TIER_A, TIER_B):
                aged += 1
                verdict = "AGED"
            else:
                scorer += 1
                verdict = "SCORER"
            details.append(f"{domain}: expected buy, tier {tier_now} at asof, "
                           f"tier {then or 'n/a'} at freshest signal {when.isoformat()}, {verdict}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return aged, scorer


def t9_run_log(asof):
    log = DATA / "runs.log"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
    if not any(l.strip() for l in lines):
        return Result("T9", "Run log", NRH,
                      "data/runs.log absent or empty. It is gitignored because it changes on "
                      "every run, so a fresh clone has no history until the pipeline is run "
                      "locally (see README, Verify it yourself)")
    names = [l.split("\t")[1] for l in lines if l.count("\t") >= 1]
    ingests, scores = names.count("ingest.py"), names.count("score.py")
    return Result("T9", "Run log", PASS if ingests >= 2 and scores >= 1 else MISS,
                  f"{ingests} ingest(s), {scores} score(s) in data/runs.log; target 2 and 1")


TARGETS = [t1_volume, t2_icp_coverage, t3_signal_types, t4_tier_a_share, t5_briefs,
           t6_decision_makers, t7_assets, t8_golden, t9_run_log]


def sample_lines(n):
    _, accounts = read_rows(DATA / "accounts.csv")
    by_id = {a.get("account_id", ""): a for a in accounts}
    all_a = tier_a_rows()
    out = [f"\nSAMPLE: {min(n, len(all_a))} of {len(all_a)} Tier A account(s), for the human checks"]
    for i, r in enumerate(all_a[:n], 1):
        acct = by_id.get(r.get("account_id", ""), {})
        brief = brief_for(r.get("account_id", ""))
        dm = acct.get("decision_maker", "").strip()
        dm_txt = (f"{dm}, {acct.get('dm_title', '').strip() or 'title unknown'} "
                  f"(source: {acct.get('dm_source', '').strip() or 'NONE'})") if dm else "none named"
        out += [f"  {i}. {r.get('company', '')} ({r.get('account_id', '')}, {r.get('icp', '')})",
                f"     score:  {r.get('score', '')}",
                f"     reason: {r.get('reason', '')}",
                f"     brief:  {brief.relative_to(ROOT).as_posix() if brief else 'MISSING'}",
                f"     dm:     {dm_txt}"]
    return out


# ---------------------------------------------------------------- main

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Run repo acceptance checks. Never modifies data/.")
    p.add_argument("--asof", help="as-of date, YYYY-MM-DD (default: today)")
    p.add_argument("--quiet", action="store_true", help="print only non-PASS checks and the summary")
    p.add_argument("--json", action="store_true", help="machine-readable output on stdout")
    p.add_argument("--strict", action="store_true", help="exit 1 on TARGET misses too")
    p.add_argument("--sample", type=int, default=0, metavar="N",
                   help="print N Tier A accounts with score, reason, brief and decision maker")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        asof = parse_date(args.asof) if args.asof else date.today()
    except ValueError:
        sys.exit(f"acceptance.py: --asof must be YYYY-MM-DD, got {args.asof!r}")

    before = hash_tree(DATA)
    results = []
    for check in CHECKS:
        try:
            results.append(check(asof))
        except Exception as e:  # a crashing check is a failing check, never a skipped one
            cid = check.__name__.split("_")[0].upper()
            results.append(Result(cid, check.__name__, FAIL, f"check crashed: {type(e).__name__}: {e}"))
    after = hash_tree(DATA)
    if before == after:
        results.append(Result("G", "data/ untouched", PASS, f"{len(after)} file(s) in data/ hash-identical before and after"))
    else:
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        results.append(Result("G", "data/ untouched", FAIL, f"data/ changed during run: {', '.join(changed)}", changed))

    targets = []
    for check in TARGETS:
        try:
            targets.append(check(asof))
        except Exception as e:  # a crashing target is a miss, never a silent skip
            cid = check.__name__.split("_")[0].upper()
            targets.append(Result(cid, check.__name__, MISS, f"check crashed: {type(e).__name__}: {e}"))

    counts = {s: sum(1 for r in results if r.status == s) for s in (PASS, FAIL, WARN, NYB)}
    core_ok = counts[FAIL] == 0
    t_pass = sum(1 for t in targets if t.status == PASS)
    t_nrh = sum(1 for t in targets if t.status == NRH)
    if not core_ok:
        verdict = "NOT WORKING"
    elif counts[PASS] == len(results) and t_pass == len(targets):
        verdict = "WORKING"
    else:
        verdict = "CORRECT BUT THIN"
    exit_code = 0 if core_ok and (not args.strict or t_pass == len(targets)) else 1

    if args.json:
        print(json.dumps({"asof": asof.isoformat(), "ok": core_ok, "verdict": verdict,
                          "strict": args.strict, "counts": counts,
                          "core": {"pass": counts[PASS], "total": len(results)},
                          "target": {"pass": t_pass, "total": len(targets)},
                          "checks": [r.as_dict() for r in results],
                          "targets": [t.as_dict() for t in targets]}, indent=2))
        return exit_code

    width = max(len(r.status) for r in results + targets)
    print("CORE: is the machine correct?")
    for r in results:
        if not (args.quiet and r.status == PASS):
            print(f"{r.status:<{width}}  {r.cid:<3} {r.name}: {r.reason}")
    print("\nTARGET: is there enough output?")
    for t in targets:
        if not (args.quiet and t.status == PASS):
            print(f"{t.status:<{width}}  {t.cid:<3} {t.name}: {t.reason}")
    if args.sample > 0:
        print("\n".join(sample_lines(args.sample)))
    print(f"\nasof {asof}. CORE: {counts[PASS]} pass, {counts[FAIL]} fail, {counts[WARN]} warn, "
          f"{counts[NYB]} not yet built. TARGET: {t_pass} pass, {len(targets) - t_pass - t_nrh} miss"
          f"{f', {t_nrh} not run here' if t_nrh else ''}"
          f"{' (--strict: misses exit 1)' if args.strict else ''}.")
    print(f"CORE {counts[PASS]}/{len(results)}   TARGET {t_pass}/{len(targets)}")
    print(f"VERDICT: {verdict}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
