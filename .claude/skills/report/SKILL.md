---
name: report
description: Summarise a run: what went in, what came out, and what was rejected. Use when asked for a report, a summary, a readout or what happened.
allowed-tools: Read, Write(out/**), Bash(python scripts/*)
---

# /report

Follow these steps in order. Do not skip, merge or reorder them.
This skill reads and summarises. It never stages, never edits a CSV, never sends.

## STEP 1 - Read the inputs
Read data/runs.log, data/killlist.csv, data/accounts.csv, data/signals.csv, data/scored.csv,
out/briefs/, out/assets/ and out/probe_log.json.
If a file is missing, note it. Do not substitute a guess.

## STEP 2 - Write out/report-<YYYY-MM-DD>.md with these sections

### What went in
Sources searched, URLs probed, candidates considered. Counts, not prose.

### What came out
Accounts by tier. Briefs written. Assets built. One line each.

### The kill list
Every company rejected or disqualified, with the reason. This section is the
point of the report: a filter that rejects nothing is not a filter.
The kill list section reads data/killlist.csv. Never rebuild it from memory
or chat; if a rejection is not in that file, it is not in the report.
Group by reason_code: suppressed, vendor, wrong_buyer, no_dated_signal,
no_evidenced_why, off_icp.
Never truncate the kill list to save space: it is the section that proves
the filter is real.

### What the probe found
The counts per verdict and what that implies about collecting this in house.

### What I would not claim
Every place the system fell short: ICPs with no accounts, signals resting on
a ceiling date, Tier A accounts whose freshest signal expires soon, checks
passing over zero rows. Be specific.

### Run the checks yourself
The exact commands. Standard library only: no pytest.
    python scripts/acceptance.py --asof <today>
    python tests/test_score_boundaries.py
    python tests/test_ingest.py
    python tests/test_dedupe.py
    python tests/test_probe.py
    python scripts/score.py --asof <today>
acceptance.py check C10 already runs every tests/test_*.py and requires
exit 0 from each, so the single acceptance command covers them all.

## STEP 3 - Run the acceptance check
Run: python scripts/acceptance.py --asof <today>
Paste its summary line into the report verbatim. Do not paraphrase a PASS.

## STEP 4 - Hard rules
- Never report a count you did not read from a file.
- If a section would be empty, write why it is empty, not nothing.
- No adjectives about the system's quality. Counts and gaps only.

## STEP 5 - Show and stop
Show the report to the human. Wait.
