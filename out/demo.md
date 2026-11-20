# Demo script, 90 seconds

Read the quoted lines aloud. Brackets say what to click.
Numbers from data/scored.csv, out/, and the acceptance run of 2026-11-20.

## 1. The output
[Open data/scored.csv, then out/briefs/]

"39 companies across three buyer types: 9 AI, 13 travel, 17 commerce.
20 have a dated, sourced signal from the last 90 days.
3 reached Tier A: Lyst, Going and Gramiyaa. Each has a first message,
drafted and not sent, that quotes their own public words with the URL.
Each comes with a teardown of the pages they would need watched, showing
where collection stopped. Gramiyaa's is on hold: pitching them would close
off a partner channel."

## 2. The design decision
"The model reads and judges; code does anything that has to be exact, so
the ranking is reproducible and the data files cannot be corrupted."

## 3. The acceptance run
[Run: python scripts/acceptance.py]

"Core checks: 11 of 11 pass. Targets: 6 of 9. Verdict: correct but thin.
Three targets miss. 39 accounts, not 40: two hunts screened about 250
companies and none met the Tier A bar. Lexroom had the date, the CEO and the
Series B, and was still dropped: it described a capability, not a gap.
I refused a filler row, because T1 and T4 pull against each other.
Tier A is 7.7 percent, under the 10 percent floor. And 3 of 7 known buyers
score A or B today; the other 4 have signals that have aged, not scoring
errors."

## 4. The probe
[Open out/assets/commerce-2026-11-20.md]

"For Gramiyaa, we tried plain collection on Blinkit, Zepto and Instamart.
0 of 7 pages returned product data. 5 got challenge pages, in 47 to 172
milliseconds. Blinkit's robots.txt refused before a page was asked for."

## THE THREE QUESTIONS

**Q1. "What did it get wrong?"**
Five golden labels were written from search snippets and failed the
evidence standard I later held the hunts to; they were corrected from
evidence, and Perplexity went to no despite a real need. A skill header
had an unquoted colon, so the skill still listed but its tool limits were
silently dropped; all six descriptions are now quoted, with a warning
comment above each.

**Q2. "What would you change with our data?"**
The weights and the suppression list. The weights are a guess checked
against 26 hand-labelled rows; your closed-won and closed-lost accounts
would let them be calibrated. Your customer list goes straight into
suppression.

**Q3. "Could this send?"**
"No send credential in this repo, and .mcp.json declares one server:
Google Sheets. It can write cells; it cannot send anything. Deny rules and
a PreToolUse hook block the obvious send paths, including MCP tools whose
names are send actions."

Then volunteer the limit, unprompted:

"My own account has Gmail and HubSpot connected, so in this session the
hook is what stands in the way, and the hook is a backstop, not a proof.
It cannot see inside a script, and the third hunt found a stdin bypass,
recorded in scope.md section 14. Clone the repo on any other machine and
there is nothing in it that can send."

[Open the /mcp panel. Project (1): sheets. The 29 below it are my
account's, inherited by every folder I open; nothing in this repo invited
them.]

Why volunteer it: stating the limit before being asked is what makes the
first half believed.

## 5. Architecture, only if asked
- CLAUDE.md: the rules. scope.md: the decisions and why.
- scripts/: ingest, score, probe, acceptance. The only writers of data/.
- .claude/hooks/guard.py: blocks sends and direct CSV edits.
- .claude/skills/: /hunt, /score, /angle, /asset, /partners, /report.
