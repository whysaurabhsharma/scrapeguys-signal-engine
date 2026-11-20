# ScrapeGuys signal engine

Finds companies with public, dated evidence that they need live web data, scores them in Python, and drafts a sourced brief and a data asset for the best of them. Built independently as an interview project, not affiliated with ScrapeGuys.

## Why this repo is private

It holds a prospect list of named companies and briefs on where each one is weak. Every claim traces to a public URL, but the companies did not ask for the assembled result, so it is not for publishing.

## Start here

- [out/demo.md](out/demo.md): the 90-second walkthrough and three prepared answers.
- [out/briefs/ac_84003d1913-going.md](out/briefs/ac_84003d1913-going.md): a sourced first touch, marked DRAFT - NOT SENT.
- [out/assets/commerce-2026-11-20.md](out/assets/commerce-2026-11-20.md): 0 of 7 quick-commerce pages returned product content to a plain client.
- [out/report-2026-11-20.md](out/report-2026-11-20.md): what went in, what came out, what was rejected and why.

## What it produced (run of 2026-11-20)

| Output | Count | File |
|---|---|---|
| Accounts | 39 (ai 9, travel 13, commerce 17) | data/accounts.csv |
| Signals | 74 (hiring 21, launch 24, funding 13, complaint 16) | data/signals.csv |
| Tiers | A 3, B 16, nurture 18, reject 2 | data/scored.csv |
| Tier A | Lyst (ai, 76.1), Going (travel, 75.1), Gramiyaa (commerce, 74.6) | data/scored.csv |
| Recorded rejections | 287 | data/killlist.csv |
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

CORE asks whether the machine is correct: 11 checks (schema, referential integrity, idempotency, determinism, provenance, dates, suppression, guard registered, never-send, the 5 test files, data/ untouched). Any CORE failure exits 1. TARGET asks whether there is enough output: 9 checks against fixed targets. Writes run inside a temp copy, so data/ is not touched.

On a clean clone T9 reports NOT RUN HERE, not MISS. data/runs.log is gitignored because it changes on every run, so a fresh clone has no history until the pipeline runs locally. NOT RUN HERE is not counted as a pass. Reproduce the run history with:

    python scripts/ingest.py --asof 2026-11-20
    python scripts/score.py --asof 2026-11-20

Three TARGET misses:
- **T1, 39 of 40 accounts, deliberately.** Hunts 6 and 7 screened about 250 companies and none met the bar. A filler row was refused: T1 and T4 pull against each other. Reason recorded in scope.md.
- **T4, Tier A 7.7%, under the 10% floor.** The evidence is thin, not the thresholds. The thresholds were fixed before any row was scored.
- **T8, 3 of 7 known buyers in A/B (43%).** All four shortfalls are AGED (they reached A/B at their freshest signal's date), none SCORER. Non-buyers handled 18 of 18.

Output of the final run, 2026-11-20, exit 0:

    CORE: is the machine correct?
    PASS  C1  Schema: all three CSV headers match common.py exactly, in order
    PASS  C2  Referential integrity: 74 signal and 39 scored row(s) all resolve to 39 account(s)
    PASS  C3  Idempotency: second ingest of 2026-11-20-accor.json, 2026-11-20-alt.json, 2026-11-20-apify.json, 2026-11-20-avantstay.json, 2026-11-20-backmarket.json, 2026-11-20-beni.json, 2026-11-20-brightdata.json, 2026-11-20-bwhhotels.json, 2026-11-20-daydream.json, 2026-11-20-elevenlabs.json, 2026-11-20-evolve.json, 2026-11-20-farmley.json, 2026-11-20-firecrawl.json, 2026-11-20-godesi.json, 2026-11-20-going.json, 2026-11-20-gramiyaa.json, 2026-11-20-hansaplast.json, 2026-11-20-henfruit.json, 2026-11-20-holidu.json, 2026-11-20-ixigo.json, 2026-11-20-lyst.json, 2026-11-20-mindtrip.json, 2026-11-20-minimalist.json, 2026-11-20-momshome.json, 2026-11-20-mtrfoods.json, 2026-11-20-onton.json, 2026-11-20-openai.json, 2026-11-20-oxylabs.json, 2026-11-20-phia.json, 2026-11-20-planetart.json, 2026-11-20-plush.json, 2026-11-20-portpro.json, 2026-11-20-prismplus.json, 2026-11-20-radisson.json, 2026-11-20-restaurantsupply.json, 2026-11-20-seon.json, 2026-11-20-sleepyowl.json, 2026-11-20-sweetkaramcoffee.json, 2026-11-20-treebo.json, 2026-11-20-troovy.json, 2026-11-20-turim.json, 2026-11-20-valamar.json, 2026-11-20-valdera.json, 2026-11-20-vogo.json, 2026-11-20-wander.json, 2026-11-20-zyte.json, EXAMPLE.json left both CSVs byte-identical (39 account row(s))
    PASS  C4  Determinism: two score runs at --asof 2026-11-20 byte-identical, 39 row(s) (data + EXAMPLE fixture)
    PASS  C5  Provenance: 74 signal(s) with http evidence_url, 33 decision maker(s) all sourced
    PASS  C6  Dates: 74 signal_date(s) ISO and <= 2026-11-20; 0 equal captured_at
    PASS  C7  Suppression: 39 account(s) checked against 16 suppress entries, none match
    PASS  C8  Guard registered: deny rules present, PreToolUse hook runs .claude/hooks/guard.py
    PASS  C9  Never-send: 0 hits in 28 file(s): .claude/agents/.gitkeep, .claude/agents/researcher.md, .claude/agents/verifier.md, .claude/hooks/.gitkeep, .claude/hooks/guard.py, .claude/rules/.gitkeep, .claude/rules/data-contract.md, .claude/settings.json, .claude/skills/.gitkeep, .claude/skills/angle/SKILL.md, .claude/skills/asset/SKILL.md, .claude/skills/hunt/SKILL.md, .claude/skills/partners/SKILL.md, .claude/skills/report/SKILL.md, .claude/skills/score/SKILL.md, .gitignore, .mcp.json, CLAUDE.md, README.md, scope.md, scripts/.gitkeep, scripts/acceptance.py, scripts/common.py, scripts/dedupe.py, scripts/ingest.py, scripts/killlist.py, scripts/probe.py, scripts/score.py
    PASS  C10 Tests: 5/5 exit 0: test_dedupe.py, test_guard.py, test_ingest.py, test_probe.py, test_score_boundaries.py
    PASS  G   data/ untouched: 53 file(s) in data/ hash-identical before and after

    TARGET: is there enough output?
    MISS  T1  Volume: 39 account(s) scored, target 40
    PASS  T2  ICP coverage: ai 9, travel 13, commerce 17; target 8 each
    PASS  T3  Signal types: 4 type(s) in use (complaint, funding, hiring, launch), target 4
    MISS  T4  Tier A share: 3/39 Tier A = 7.7%, target 10-40%
    PASS  T5  Briefs: 3/3 of the first ten Tier A have a brief in out/briefs/
    PASS  T6  Decision makers: 3/3 Tier A have a named decision maker with dm_source, target half
    PASS  T7  Assets: 3/3 ICP asset(s) carry a number in their first three lines
    MISS  T8  Golden set: buyers callable now: matched 7/8, in A/B at asof 3/7 = 43% (of 4 below B: 4 AGED, A/B at their freshest signal's date; 0 SCORER, nurture even then); non-buyers matched 18/18 (0 scored, 18 declined in killlist.csv), handled 18/18 = 100%; target 80% each
    PASS  T9  Run log: 11 ingest(s), 11 score(s) in data/runs.log; target 2 and 1

    asof 2026-11-20. CORE: 11 pass, 0 fail, 0 warn, 0 not yet built. TARGET: 6 pass, 3 miss.
    CORE 11/11   TARGET 6/9
    VERDICT: CORRECT BUT THIN

## What this does badly

- **Going leaves Tier A on 2026-12-22.** Its freshest signals are Ashby `publishedAt`, ceiling dates. Its only exact-dated signal is the 2026-09-23 launch.
- **Gramiyaa's pain evidence comes from its incumbent vendor.** The complaint source is an Inc42 series co-produced with Nitro Commerce. Funding date is approximate. Brief HELD.
- **Tier A is 3 accounts.** One per ICP; the ai Tier A, Lyst, rests on 3 Trustpilot reviews plus one ceiling-dated hiring signal.
- **32 of 74 signals lack an exact date:** 14 ceiling, 18 approx.
- **183 of 287 kill-list rows have no source URL.** The rejection stands but cannot be re-checked.
- **Searches per hunt were never logged.** data/runs.log records ingests and scores, not queries, so the funnel starts at candidates screened.
- **6 of 39 accounts have no named decision maker.**

## What I learned building it

1. **ATS search finds roles, not buyers** (scope.md 9). One `site:jobs.ashbyhq.com "web scraping"` query returned eight companies on 2026-11-19; in the first real hunt vendor listings dominated, and two of three accounts came from checking likely companies' job boards directly.
2. **Seed lists failed 3 of 4 times** (scope.md 9). A quick-commerce brand directory shows who sells there, not who has said they cannot see it. Vendor case studies and founder interviews found Farmley, Gramiyaa and Moms Home.
3. **The ai ICP is a narrower buyer than assumed** (scope.md 9). AI shopping and travel assistants either crawl for themselves or source through a platform API. Wanderlog, Recipy and Product.ai were each rejected on that pattern.
4. **A disclaimer is not a confession** (scope.md 9). Ludex admitted its prices are a day stale; Zyft disclaimed stock accuracy. Neither said it cannot see something. Both golden buy labels failed.
5. **A complaint alone can never reach Tier A** (scripts/common.py). Weight 12, halved by an approx date, against a Tier A pain minimum of 15. This emerged from the weights rather than being chosen; it is recorded so it is a decision.
6. **The first run produced 0 Tier A, and the thresholds stayed** (scope.md 13). SEON scored 56.2 on a ceiling-dated hiring signal 57 days into a 60-day half-life.
7. **A data-contract bug cost Lyst its tier** (scope.md 14). Ingest accepted stage values outside the allowed set, which score.py read as unknown. The fix moved Lyst 67.7 to 76.1, B to A, and Back Market +10 with no tier change.
8. **The hook was bypassed in practice** (scope.md 14). A stdin heredoc got Python past guard.py. The never-send guarantee was rewritten to rest on what the repo lacks, not on what the hook catches.
9. **An unquoted colon in skill frontmatter dropped allowed-tools silently** (scope.md 14). The skill still listed and ran, without its tool limits. All six descriptions are now quoted, with a comment above each.
