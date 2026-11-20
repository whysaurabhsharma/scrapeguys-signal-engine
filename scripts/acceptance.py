"""Acceptance checks for the repo. Standard library only.

Prints PASS, FAIL, WARN or NOT YET BUILT for each check with a one-line
reason, then a summary. Exits 1 if any check FAILs.

Never modifies data/. Anything that writes (ingest, score) runs inside a
temporary copy of scripts/, config/ and data/, so ROOT in those scripts
resolves to the copy. data/ is hashed before and after the run and the
result is reported as a final guard check.

    python scripts/acceptance.py [--asof YYYY-MM-DD] [--quiet] [--json]
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

PASS, FAIL, WARN, NYB = "PASS", "FAIL", "WARN", "NOT YET BUILT"


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
        reader = csv.reader(f)
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


# ---------------------------------------------------------------- main

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Run repo acceptance checks. Never modifies data/.")
    p.add_argument("--asof", help="as-of date, YYYY-MM-DD (default: today)")
    p.add_argument("--quiet", action="store_true", help="print only non-PASS checks and the summary")
    p.add_argument("--json", action="store_true", help="machine-readable output on stdout")
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

    counts = {s: sum(1 for r in results if r.status == s) for s in (PASS, FAIL, WARN, NYB)}
    ok = counts[FAIL] == 0

    if args.json:
        print(json.dumps({"asof": asof.isoformat(), "ok": ok, "counts": counts,
                          "checks": [r.as_dict() for r in results]}, indent=2))
    else:
        width = max(len(r.status) for r in results)
        for r in results:
            if args.quiet and r.status == PASS:
                continue
            print(f"{r.status:<{width}}  {r.cid:<3} {r.name}: {r.reason}")
        print(f"\nSummary (asof {asof}): {counts[PASS]} pass, {counts[FAIL]} fail, "
              f"{counts[WARN]} warn, {counts[NYB]} not yet built. {'OK' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
