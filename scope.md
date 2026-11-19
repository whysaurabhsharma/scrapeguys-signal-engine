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
