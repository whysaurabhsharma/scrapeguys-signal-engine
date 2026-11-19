# ScrapeGuys signal engine

Built independently as an interview project. Not affiliated with ScrapeGuys.

## What this system does

Finds companies showing public, dated evidence that they need live web data,
scores them deterministically, and writes a sourced brief plus a data asset
for the best of them. It drafts. A human sends.

## Operating rules

1. NEVER SEND. No email, no DM, no form post, no CRM send tool. Every draft
   is a file marked DRAFT - NOT SENT. There is no send credential in this repo.
2. PUBLIC SOURCES ONLY. If a signal exists only behind a login, it does not
   exist for this system. Respect robots.txt. Documented public APIs are fine.
3. NO CLAIM WITHOUT A URL. Anything unsourced is written as UNVERIFIED or not
   written at all. An empty field beats a guessed one.
4. NO DATE, NO SIGNAL. signal_date is when the event happened, never today.
   An undated signal is dropped, not estimated.
5. SCRIPTS WRITE THE CSVs. Never edit accounts.csv, signals.csv or scored.csv
   directly. Write JSON to data/staging/ and run scripts/ingest.py.
6. NEVER SCORE BY HAND. Do not invent or adjust a score, a tier or an id.
   If the ranking is wrong, the weights are wrong: propose, wait, re-run.
7. HUMAN-FACING OUTPUT: finding first, method second, nothing over 200 words.

## Disqualify

- Scraping, proxy and extraction vendors. They hire scraping engineers
  because it is their product, not their pain.
- Anything in config/suppress.csv.
- Frontier AI labs and hyperscalers running web-scale crawling as core
  infrastructure (OpenAI, ElevenLabs and similar). Real signal, wrong buyer.
  This is a narrow exclusion: having engineers is not a reason to disqualify.
  Most buyers here have an engineering team and still do not want to run
  proxy pools.

## The three ICPs

| icp | What they lack | Market |
|---|---|---|
| ai | A live view of the web their product answers from. Prices and availability go stale between crawls, so the user is shown something no longer true. | Global |
| travel | Sight of their own rates across the OTAs reselling them. Parity leaks go unseen until revenue has moved. | Global |
| commerce | Live visibility of their SKUs and competitors across quick-commerce and marketplaces, where price, stock and placement change hourly. | India first: Blinkit, Zepto, Instamart |

## Signal types, and where the date comes from

| type | Date source |
|---|---|
| hiring | ATS public JSON API, never the HTML page. Greenhouse first_published is preferred. Ashby publishedAt is LAST published, so treat it as a ceiling. |
| funding | Announcement date. The most reliable trigger. |
| launch | Press or product announcement date. |
| complaint | Public post date. |

## Tiers

A = 70, B = 50, nurture = 30, reject below 30.
Fixed before any row was scored. Not to be changed to flatter a result.
No pain means nurture at best. Tier A needs a trigger from the last 90 days.

## Repo map

    scope.md             The decisions, and why. Read before changing anything.
    CLAUDE.md            This file.
    .claude/skills/      The six workflows, invoked with a slash command.
    .claude/agents/      researcher, verifier. Read-only subagents.
    .claude/rules/       Path-scoped rules. data-contract.md loads on data/**.
    .claude/hooks/       guard.py. Blocks sends and direct CSV edits.
    scripts/             common.py, ingest.py, score.py, dedupe.py,
                         probe.py, acceptance.py. The only writers.
    config/              suppress.csv, seeds/
    data/staging/        JSON the agent writes. Input to ingest.py.
    data/                accounts.csv, signals.csv, scored.csv, runs.log
    tests/golden.csv     Hand-labelled buyers and non-buyers.
    out/briefs/          One per Tier A account.
    out/assets/          One per ICP.

## Workflow order

    /hunt     discover, confirm, disqualify, stage, ingest
    /score    run scripts/score.py and interrogate the ranking
    /angle    one brief per Tier A account
    /asset    the ICP-specific data asset, the differentiator
    /partners the partner archetypes, kept separate from accounts
    /report   inputs, outputs, and a kill list

## This machine

Python is invoked as "python", not "python3". Use it in settings.json,
hooks, skills and all dynamic-context lines.

