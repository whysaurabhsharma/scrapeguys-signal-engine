---
name: partners
# keep quoted: an unquoted description breaks every key below it, and the skill still lists but loses allowed-tools
description: "Identify partner archetypes who could resell or refer live-data collection, kept separate from the account pipeline. Use when asked about partners, channels, resellers or referrals."
allowed-tools: Read, Write(out/**), WebSearch, WebFetch
---

# /partners

Follow these steps in order. Do not skip, merge or reorder them.
This skill documents. It never stages, never edits a CSV, never sends.

## STEP 1 - Partners are NOT accounts
Never write a partner into data/staging/, accounts.csv or signals.csv.
Partners go only to out/partners.md. State this at the top of that file.

## STEP 2 - Identify 4 to 6 ARCHETYPES, not companies
An archetype is a kind of business that already sits between the buyer and
their data problem. For each, name 2 to 3 real examples with URLs, as
illustration only. Archetypes to consider for these ICPs:
- quick-commerce and marketplace agencies serving many D2C brands at once
- pricing and revenue-management software whose product needs a live feed
- hotel and travel distribution consultants
- AI application builders who need current web facts their model lacks
- data and analytics consultancies delivering client dashboards
- ecommerce platform or ERP integrators

## STEP 3 - Profile each archetype
For each, write:
- who they serve, and roughly how many clients one of them touches
- what they currently do instead, and why it is painful
- what they would resell or refer, in one sentence
- the one objection they would raise first
- refer, resell or white-label, and why

## STEP 4 - Rank by reach per conversation
Rank the archetypes by how many end buyers one partner conversation could
reach. State the reasoning for each position, not just the order.

## STEP 5 - Hard rules
- Every named example needs a URL.
- Do not claim client counts you cannot source. Write UNVERIFIED instead.
- Do not write a partner into any CSV.
- Disqualify rules from CLAUDE.md still apply: no scraping, proxy or
  extraction vendors as partners.

## STEP 6 - Write and stop
Write out/partners.md, show it, and wait for the human.
Finding first, method second.
Do not shorten the STEP 4 ranking reasoning to save space. It is the part
that makes this a strategy rather than a list.
