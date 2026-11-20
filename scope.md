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
- commerce      India-first: Blinkit, Zepto, Instamart, Indian marketplaces.
- ai, travel    Global.
Recorded per account in the country column. /hunt applies it per ICP.

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
           Only documented endpoints. jobs.ashbyhq.com/api/ is robots-disallowed.
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
