---
name: angle
description: Write a sourced first-touch brief for each Tier A account. Use when asked for angles, briefs, outreach drafts or what to say to an account.
allowed-tools: Read, Write(out/briefs/**), WebSearch, WebFetch
---

# /angle

Follow these steps in order. Do not skip, merge or reorder them.
This skill drafts. It never sends, never edits a CSV, never changes a score.

## STEP 1 - Take Tier A only

Read `data/scored.csv`. Keep rows where `tier` is `A`.
If there are none, say "No Tier A accounts. No briefs written." and stop.
Do not write briefs for Tier B, nurture or reject.

## STEP 2 - Gather the evidence

For each Tier A account, read its rows in `data/signals.csv` and
`data/accounts.csv` (match on `account_id`). Every claim in the brief must
trace to one of those rows or to a URL you fetch now. If you cannot source
a claim, leave it out.

## STEP 3 - Write the brief

Write `out/briefs/<account_id>-<slug>.md` (slug: lowercase company name,
hyphens) with exactly these sections:

    # <Company>
    DRAFT - NOT SENT

    ## The signal
    What they published, when, with the URL. One short paragraph.

    ## What they cannot see
    One sentence naming the specific thing live data would show them that
    they currently cannot see. Not "they need data".

    ## The cost of not seeing it
    Two sentences at most, and only if tied to something public: their own
    job description, their pricing page, their public statements. If not,
    write "UNVERIFIED - no public evidence of the cost" and stop there.
    An empty section beats an invented one.

    ## The opening line
    One sentence a human could actually send. It must reference the signal
    by name and date. No flattery, no "I noticed", no "hope this finds you".

    ## Sources
    Every URL used, as a list.

## STEP 4 - Hard rules

- Line 2 of every file is `DRAFT - NOT SENT`. Never remove it.
- Never write an email address, a phone number or a LinkedIn message.
- Never claim a person said something without the URL where they said it.
- Under 200 words per brief, excluding Sources.

## STEP 5 - STOP

List the briefs written (path, company). Show one in full. Wait.
