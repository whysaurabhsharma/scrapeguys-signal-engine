---
name: hunt
description: Find companies showing public dated evidence of needing live web data, verify each one, and stage them for ingest. Use when asked to find, hunt, source or discover accounts.
allowed-tools: WebSearch, WebFetch, Read, Write(data/staging/**), Bash(python scripts/*)
---

# /hunt

Follow these steps in order. Do not skip, merge or reorder them.
This skill drafts and stages. It never sends anything to anyone.

## STEP 1 - Read first

Read, in full:
- `scope.md` sections 8-11 (date sources, ranked discovery sources,
  first candidates, suppression lessons)
- `config/suppress.csv`
- `data/staging/EXAMPLE.json`

Do not skip. EXAMPLE.json is the shape to copy, field for field.

## STEP 2 - Discover

Use only sources ranked WORKS in scope.md section 9. The primary source is
ATS-targeted search:

    site:jobs.ashbyhq.com "<pain phrase>"
    site:boards.greenhouse.io "<pain phrase>"
    site:jobs.lever.co "<pain phrase>"

Vary the pain phrase: web scraping, data acquisition, price intelligence,
competitor pricing, rate parity, catalogue data, anti-bot, proxy rotation.

Do NOT use generic funding search. scope.md records that it returns noise.

Apply the market rule per ICP (scope.md section 4): all three ICPs are
global. For commerce, India is preferred where the evidence is equally
strong.
- Sub-case, Indian D2C brands: scope.md section 9 says search returns market
  reports, not brands, so start from the seed lists in `config/seeds/`.

## STEP 3 - Date every candidate from the ATS JSON API

Never take a date from the HTML job page. Use the documented endpoints in
scope.md section 8 and set `date_confidence`:

| ATS | Field | date_confidence |
|---|---|---|
| Greenhouse | `first_published` (not `updated_at`) | exact |
| Ashby | `publishedAt` (last published) | ceiling |
| Lever | `createdAt` (unix ms) | exact |

If no machine-readable date exists, the signal is `approx` and must not be
the only basis for a Tier A claim. No date at all: drop the signal.

Gather evidence with the `researcher` subagent, one company at a time, then
check it with the `verifier` subagent. Pass the verifier ONLY a flat list of
claims with their URLs: never the researcher's reasoning, its conclusion
about fit, or its one-sentence why. The check is only independent if the
verifier has not read the argument.
Stage a signal only if the verifier returns SUPPORTED for its date AND its
evidence URL. PARTIAL, UNSUPPORTED or UNREACHABLE: not staged, reason in STEP 7.

## STEP 4 - Disqualify before researching further

Drop, and print one line per drop with its reason:
- anything in `config/suppress.csv`
- any scraping, proxy or extraction vendor
- any frontier AI lab or hyperscaler running web-scale crawling as core
  infrastructure

Format: `DISQUALIFIED  <company>  <reason>`. Never drop silently.
Having an engineering team is not a reason to disqualify.

Every disqualification here, and every drop in any later step (STEP 5's
`DROPPED`, a verifier failure, an account with no dated signal), is
appended to `data/killlist.csv` AT THE TIME IT HAPPENS, not only reported
in chat:

    python scripts/killlist.py --date <today> --company "<name>" \
        --domain <domain> --reason-code <code> --reason "<why>" \
        --source-url <url>

reason_code: suppressed, vendor, wrong_buyer, no_dated_signal,
no_evidenced_why, off_icp. Leave domain or source_url empty rather than
guess. A rejection that exists only in a transcript cannot appear in the
kill list later.

## STEP 5 - Write why_live_data

For each survivor, write `why_live_data` as ONE sentence naming what this
company specifically cannot see without live data. Not "they need data".

If you cannot write that sentence from the evidence you fetched, drop the
account and print `DROPPED  <company>  no evidenced why_live_data`.

## STEP 6 - Stage

Write `data/staging/<YYYY-MM-DD>-<slug>.json`, copying the shape of
EXAMPLE.json exactly.

- Never invent `account_id` or `signal_id`. Scripts assign them.
- Never set `signal_date` to today. It is when the event happened.
- Every claim carries a URL. Unsourced fields stay empty.
- Never touch accounts.csv, signals.csv or scored.csv.

## STEP 7 - STOP

Show a table of what you staged:

| company | icp | signal type | signal date | date confidence | why_live_data |
|---|---|---|---|---|---|

Under it, list disqualified and dropped companies, and unstaged signals with
the verifier's verdict. Then wait for the user's go-ahead. Do not run ingest without it.

## STEP 8 - Ingest, only after approval

Dry run first. A staging file with a systematic error, such as the wrong
date field or a missing `date_confidence`, must be caught before it
touches the CSVs, not after.

    python scripts/ingest.py --asof <today> --dry-run

Read every `REJECTED` line out to the user. Fix the research, not the
record: re-fetch the source, correct the staged JSON from evidence, re-run
the dry run. Never edit a field just to make it pass. Repeat until the dry
run is clean, or every remaining rejection is one you can explain.

Only then run the real ingest:

    python scripts/ingest.py --asof <today>

Report the five ingest counts: accounts added, accounts updated,
signals added, signals duplicate, records rejected.
