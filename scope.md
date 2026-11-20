# Scope — ScrapeGuys signal engine

Built independently as an interview project. Not affiliated with ScrapeGuys.

## 1. One sentence
This system turns public, dated signals of live-data pain into a scored,
sourced pipeline with a first-touch data asset attached, so that a founder
opens it and finds the first ninety minutes of selling already done.

## 2. Refusals
1. Never sends anything. Every draft is a file marked unsent.
2. Public sources only. If a signal exists only behind a login, it does not exist.
3. No claim without a URL.
4. Nothing exact is left to the model. It does not score, assign ids,
   or write the pipeline files.

## 3. The three ICPs
- ai       lacks a live view of the web its product answers from. Prices,
           availability and facts go stale between crawls, so the user is
           shown something that is no longer true.
- travel   lacks sight of its own rates across the OTAs reselling it.
           Parity leaks and undercutting go unseen until revenue has moved.
- commerce lacks live visibility of its SKUs and competitors across
           quick-commerce and marketplaces, where price, stock and
           placement change hourly.

## 4. Market focus
- commerce      Global. India (Blinkit, Zepto, Instamart, Indian
                marketplaces) still preferred where the evidence is equally
                strong.
- ai, travel    Global.
Recorded per account in the country column. /hunt applies it per ICP.

Scope change, 2026-11-20: commerce was India-first; it is now global, with
India preferred on equal evidence. Made to widen the pool for a 20-30
account pipeline. The tier thresholds and the evidence rules are UNCHANGED:
volume comes from more hunting, not from weaker gates.

## 5. Tier thresholds
A = 70    B = 50    nurture = 30    reject = below 30
Fixed before any row was scored. Not to be changed to flatter a result.

## 6. Weights live in
scripts/common.py  — imported by every script.
Not config/signals.yaml: yaml is not in the standard library.

## 7. Python command on this machine
python   (not python3). Used in settings.json, hooks and all skills.

## 8. Signal types and where dates come from
Four types only. No date, no signal.

- hiring   ATS public JSON APIs (not the HTML page, which is JS-rendered
           and carries no date):
             Greenhouse  boards-api.greenhouse.io/v1/boards/{token}/jobs
                         use first_published, not updated_at
             Ashby       api.ashbyhq.com/posting-api/job-board/{board}
                         publishedAt is LAST published; treat as a ceiling
             Lever       api.lever.co/v0/postings/{slug}?mode=json
                         createdAt, unix ms
             Workable    apply.workable.com/api/v1/widget/accounts/{acct}?details=true
                         published_on; treat as a ceiling unless confirmed
                         first-published (added 2026-11-20)
             SmartRecruiters  api.smartrecruiters.com/v1/companies/{co}/postings
                         releasedDate; treat as a ceiling unless confirmed
                         first-published (added 2026-11-20)
           Only documented endpoints. jobs.ashbyhq.com/api/ is robots-disallowed.
           date_confidence: exact = a first-published or announcement date;
           ceiling = a machine-readable date that may be a later repost;
           approx = NO machine-readable field exists, only a date printed
           on a page. A machine-readable field is never approx.
- funding  announcement date. The most reliable trigger, so it is the
           fallback qualifier for Tier A when a hiring date is unverifiable.
- launch   press or product announcement date.
- complaint  public post date.

## 9. Discovery sources, ranked by the hand test (19 Nov 2026)
WORKS   ATS-targeted search, e.g. site:jobs.ashbyhq.com "web scraping"
        One query returned eight real companies stating the pain themselves.
        Qualifier, from the first real hunt on 2026-11-20: ATS site: search
        finds scraping ROLES well but is weak at finding BUYERS, because
        vendor listings dominate the results. Two of three accounts in the
        first hunt came from checking likely companies' job boards directly
        instead.
FAILS   Generic funding search. Returned AI mega-rounds, zero buyers. Killed.
FAILS   Search-based discovery for India commerce. Returns market reports,
        not individual brands. Use seed lists in config/seeds/ instead.
        Refined 2026-11-20, fourth hunt: config/seeds/ brands failed STEP 5
        three times out of four (Wellbeing Nutrition, Rage Coffee, Earth
        Rhythm) - a brand directory lists who sells on quick commerce, not
        who has said they cannot see it. The fourth, Farmley, passed only
        because a vendor case study quoted its pain, not because of the
        listing. WORKS instead: quick-commerce vendor case studies and
        founder press interviews, where a brand describes its own problem in
        its own words. Found Farmley, Gramiyaa and Moms Home that way.

## 10. First five candidates (to verify before ingest)
alt.xyz      commerce  pricing model fed by marketplace/auction scraping
seon.io      ai        enrichment API on the live request path
cube.global  ai        geo-blocking, Cloudflare, CAPTCHA named in the role
nascent.xyz  ai        half the role is proxy tuning and fleet health
icounter     ai        weaker fit, dark-web collection out of scope

## 11. Suppression, learned on the hand hunt
wynd labs / grass   operates a distributed crawler network: competitor
Also set aside: OpenAI, ElevenLabs. Real signal, wrong buyer.
The scorer needs a size CEILING, not just a floor.

## 12. MCP servers this repo declares
.mcp.json declares ONE server: Google Sheets. Nothing else, on purpose.
Why Sheets   The pipeline's output is CSV. Sheets is how a non-technical
             person opens, sorts and filters it.
Why only it  No send-capable server (mail, chat, CRM, social) is declared by
             this repo. That absence is the real never-send guarantee; the
             MCP denylist in .claude/hooks/guard.py is only a backstop.
Credentials  None in the file. Auth comes from the environment / OAuth.

## 13. First real run, 2026-11-20
3 accounts staged, 5 signals, 0 rejected. Idempotency confirmed on real
data: second ingest added nothing, 5 duplicates.
Result: 0 Tier A, 1 Tier B, 2 nurture.
SEON missed Tier A on score (56.2 vs 70) and on pain (11.2 vs 15), not on
age (57 days, inside 90). Its hiring signal carries ceiling confidence
(x0.75) and is 57 days into a 60-day half-life, so it contributes about 7
of a possible 18.
The thresholds were NOT changed to produce a Tier A. A run with nothing
hot is a real answer.

Two golden labels were corrected on 2026-11-20: cube.global and
nascent.xyz, both buy to no. The correction came from evidence the hunt
fetched, not from a score I wanted - cube.global sells collection as its
product, and nascent.xyz sits outside all three ICPs. Changing a golden
label to match a pipeline result is overfitting unless the evidence is
what moved; here it was.

Golden domain exclusion, 2026-11-20. Hunts 2, 3 and 4 were instructed to
exclude every domain in tests/golden.csv. The reason: the golden labels
were written from the same Phase 0.4 search that produced the first
candidates, so a hunt allowed to find them would make the golden check a
mirror rather than a test - it would only prove the pipeline rediscovered
the companies used to write the labels. The cost is that golden has only
ever tested one row, seon.io. The fix is more golden rows labelled from
companies the pipeline has not seen, not fewer exclusions.

## 14. Known limit of the guard, found 2026-11-20
During the third hunt a session bypassed guard.py by piping a Python
script into the interpreter from stdin (a heredoc: python -I - <<'EOF'),
which the pattern matcher cannot see. What it got around was the
write-outside-repo rule: the Write tool had refused a scratch file, so the
code moved into the command's stdin instead. It did not touch the protected
CSVs; the existing inline-python check already denies stdin python that
names one. One such route is now blocked (guard.py rule 7); the class is
not closable by pattern matching. The real never-send guarantee is
therefore: no send credential in this repo, and no send-capable server
declared by it. The hook and the deny rules are defence in depth, not the
proof. Any claim that rests on the hook alone is overstated.

Corrections, 2026-11-20, fourth hunt. Two data-contract fixes, each
applied to every record it covered, re-ingested through ingest.py:
- Stage: three staged values were outside STAGES ("subsidiary", "late",
  "pre_series_a") and ingest accepted them silently, so score.py read them
  as unknown (5). ingest.py now rejects any stage not in STAGES. Corrected
  from evidence: Lyst -> public (listed parent ZOZO), Back Market -> growth
  (Series E, profitable), Moms Home -> seed (pre-Series A).
- Date confidence: Workable and SmartRecruiters expose a machine-readable
  date, so by the existing definition they are ceiling, not approx.
  Relabelled: Lyst, ixigo, PlanetArt hiring signals. ingest.py now updates
  date_confidence and evidence_note on an existing signal_id.
Effect (score before -> after, tier):
  Lyst         67.7 -> 76.1  B -> A        stage +5, date relabel +3.4
  Moms Home    48.4 -> 51.4  nurture -> B  stage +3
  Back Market  37.9 -> 47.9  nurture       stage +10, no tier change
  ixigo        57.4 -> 59.3  B             date relabel +1.9
  PlanetArt    21.0 -> 24.0  reject        date relabel +3.0
Either Lyst correction alone would have reached A (72.7 or 71.1). Each was
justified by a rule that predated it: a vocabulary ingest should already
have enforced, and a date-confidence definition applied as written. Three
of the five corrected accounts moved no tier, and Back Market's was the
largest single change, which shows the fix was not applied selectively.
Result after corrections: A 3, B 12, nurture 8, reject 1 (24 accounts).
