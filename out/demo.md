# Demo script, a two-minute opening

**The only hard rule: stop talking whenever a file is open.** He reads
faster than you talk, and silence while he reads is not dead air.

This is not a 90-second script. It is a two-minute opening for a
conversation that will be interrupted: 282 spoken words, roughly two
minutes of talking, plus time while files are on screen.

Read the quoted lines aloud. Brackets say what to click.
Words in {braces}: drop them if the room is rushed. Everything else stays.
Numbers from data/scored.csv, out/, and the acceptance run of 2026-11-20.

## 1. The opening
Spoken to the ScrapeGuys CEO, Growth Manager interview.

> **Do NOT claim a sample of the company's own data is attached.** Nothing
> was collected. The assets are documented gaps, and out/probe_log.json
> shows that in four seconds if the claim is overstated.

"Your job description says inbound is being built from zero and the Growth
Manager has to find where the buyers are. I didn't want to answer that with
a plan, so I built the first version of the answer.

It's a machine that looks for public signs that a company needs live web
data right now, ranks them, and drafts the first message with a teardown of
that company's own pages, showing where collection breaks.

I ran your pitch on myself, without your keys. Zero of seven quick-commerce
pages returned product data: five served challenge pages, and Blinkit's
robots.txt refused before the other two were requested. That is your entire
sales argument, and I now believe it from the inside rather than from your
homepage.

I built it because it's the actual job: client acquisition and channel
discovery are the top two things in the role.

It never sends anything. It prepares the work; a person decides."

## 2. The design decision
"The model reads and judges; code does anything that has to be exact{, so
the ranking is reproducible and the data files cannot be corrupted}."

## 3. The acceptance run
[Run: python scripts/acceptance.py]

"Core checks: 11 of 11 pass. Targets: 6 of 9. Verdict: correct but thin.
Three targets miss. 39 accounts, not 40: two hunts screened about 250
companies and none met the Tier A bar. Lexroom had the date, the CEO and the
Series B, and was still dropped: it described a capability, not a gap.
I refused a filler row, because T1 and T4 pull against each other.
{Tier A is 7.7 percent, under the 10 percent floor.} And 3 of 7 known buyers
score A or B today; the other 4 have signals that have aged, not scoring
errors."

## 4. The probe
[Open out/assets/commerce-2026-11-20.md and stop talking.]

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
