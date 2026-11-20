# ScrapeGuys signal engine

Finds companies with public, dated evidence that they need live web data, scores them in Python, and drafts a sourced brief and a data asset for the best of them. Built independently as an interview project, not affiliated with ScrapeGuys.

## Why this repo is private

It holds a prospect list of named companies and briefs on where each one is weak. Every claim traces to a public URL, but the companies did not ask for the assembled result, so it is not for publishing.

## Start here

- [out/briefs/ac_84003d1913-going.md](out/briefs/ac_84003d1913-going.md): a sourced first touch, marked DRAFT - NOT SENT.
- [out/assets/commerce-2026-11-20.md](out/assets/commerce-2026-11-20.md): 0 of 7 quick-commerce pages returned product content to a plain client.
- [out/report-2026-11-20.md](out/report-2026-11-20.md): what went in, what came out, what was rejected and why.

## What it produced (run of 2026-11-20)

| Output | Count | File |
|---|---|---|
| Accounts | 24 (ai 7, travel 8, commerce 9) | data/accounts.csv |
| Signals | 47 (hiring 13, launch 20, funding 7, complaint 7) | data/signals.csv |
| Tiers | A 3, B 12, nurture 8, reject 1 | data/scored.csv |
| Tier A | Lyst (ai, 76.1), Going (travel, 75.1), Gramiyaa (commerce, 74.6) | data/scored.csv |
| Recorded rejections | 58 | data/killlist.csv |
| Briefs | 3, one per Tier A; Gramiyaa HELD | out/briefs/ |
| Assets | 3, one per ICP | out/assets/ |
| URLs probed | 27: usable 8, blocked 8, robots-skipped 6, error 4, JS 1 | out/probe_log.json |

## The design decision

The model does judgment: finding candidates, reading evidence, deciding if a company is a buyer, writing briefs. Python does anything that must be exact. The model never scores, never assigns an id, never writes a CSV.

- [scripts/common.py](scripts/common.py): weights, tier thresholds (A 70, B 50, nurture 30), id generation.
- [scripts/ingest.py](scripts/ingest.py): the only path from data/staging/*.json into accounts.csv and signals.csv. Rejects stages outside the allowed set.
- [scripts/score.py](scripts/score.py): the only writer of scored.csv.
- [.claude/settings.json](.claude/settings.json): denies Edit on the three pipeline CSVs.
- [.claude/hooks/guard.py](.claude/hooks/guard.py): blocks direct CSV writes from Bash, Write and Edit.

## Never sends

There is no send credential in this repo, and [.mcp.json](.mcp.json) declares one server, Google Sheets, which cannot send. That is the guarantee.

Deny rules in settings.json and a PreToolUse hook (guard.py) block the obvious paths: send libraries, mail and webhook hosts, and MCP tools whose name is a send action. The hook is a backstop, not a proof. It cannot see inside a script. During the third hunt a session bypassed it by piping Python into the interpreter on stdin. guard.py rule 7 now blocks that route; the class of bypass cannot be closed by pattern matching. See [scope.md](scope.md) section 14.

## Verify it yourself

    python scripts/acceptance.py --asof 2026-11-20

Runs 11 checks and exits 1 on any failure. Writes run inside a temp copy, so data/ is not touched.

- C1 schema, C2 referential integrity: every CSV matches its header contract; every signal points to a real account.
- C3 idempotency: ingesting the same staging twice adds nothing.
- C4 determinism: scoring twice gives identical output.
- C5 provenance, C6 dates: every signal has an http evidence URL and every named decision maker a source; every signal date is a real ISO date no later than `--asof`, with a warning if most equal the capture date.
- C7 suppression: nothing in config/suppress.csv reached the pipeline.
- C8 guard registered, C9 never-send: the hook is wired in; no send library or host in the code.
- C10 tests: runs every tests/test_*.py (5 files: dedupe, guard, ingest, probe, score boundaries).
- G: data/ is hash-identical before and after the run.

Last result: 11 pass, 0 fail, 0 warn.

    python scripts/score.py --asof 2026-11-20

Recomputes scored.csv from accounts.csv and signals.csv. Same `--asof`, same result: no score was set by hand.

## What this does badly

- **Going leaves Tier A on 2026-12-22.** Its freshest signal is an Ashby `publishedAt`, a ceiling date. Its only exact-dated signal is the 2026-09-23 launch.
- **Gramiyaa's pain evidence comes from its incumbent vendor.** The complaint source is an Inc42 series co-produced with Nitro Commerce. Funding date is approximate. Brief HELD.
- **16 of 47 signals lack an exact date:** 8 ceiling, 8 approx.
- **17 of 58 kill-list rows have no source URL.** The rejection stands but cannot be re-checked.
- **Searches per hunt were never logged.** The funnel starts at 82 candidates, not at queries.
- **The golden set tested one row.** tests/golden.csv has 20 labels; only seon.io ever reached accounts.csv, because later hunts excluded golden domains by design. The score skill's golden check has had one data point.
- Lyst's pain rests on 3 Trustpilot reviews. 5 accounts have no sourced decision maker.

## What I learned building it

1. **ATS search finds roles, not buyers** (scope.md 9). On 2026-11-19 one `site:jobs.ashbyhq.com "web scraping"` query returned eight companies. In the first real hunt on 2026-11-20, vendor listings dominated; two of three accounts came from checking likely companies' job boards directly.
2. **Seed lists failed 3 of 4 times** (scope.md 9). A quick-commerce brand directory shows who sells there, not who has said they cannot see it. Vendor case studies and founder interviews found Farmley, Gramiyaa and Moms Home.
3. **The first run produced 0 Tier A, and the thresholds stayed** (scope.md 13). SEON scored 56.2: a ceiling-dated hiring signal 57 days into a 60-day half-life contributed about 7 of 18 points.
4. **A data-contract bug cost Lyst its tier** (scope.md 14). Ingest silently accepted stage values outside the allowed set, which score.py read as unknown. Fixing that and a date-confidence label moved Lyst 67.7 to 76.1, B to A. The same fix moved Back Market +10 with no tier change.
5. **The hook was bypassed in practice** (scope.md 14). A stdin heredoc got Python past guard.py. The never-send guarantee was rewritten to rest on what the repo lacks, not on what the hook catches.
