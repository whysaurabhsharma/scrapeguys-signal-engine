---
name: asset
description: Build the small ICP-specific data asset that goes with a first touch, or the probe evidence that stands in for it. Use when asked for an asset, a sample, a teardown or proof.
allowed-tools: Read, Write(out/assets/**), Bash(python scripts/*), WebSearch, WebFetch
---

# /asset

Follow these steps in order. Do not skip, merge or reorder them.
This skill documents. It never invents data, never edits a CSV, never sends.

## STEP 1 - Pick the ICP
Ask which ICP, or infer it from the account named (its icp in data/scored.csv).
The asset differs per ICP:
- **ai** - freshness teardown. Pick 5 facts their product would answer from
  (prices, availability, specs). Show which are stale or unobtainable without
  live collection.
- **travel** - rate-visibility teardown. Pick one property or route. Show what
  a supplier cannot see about its own rates across resellers.
- **commerce** - shelf teardown. Pick 5 SKUs. Show what changes hourly across
  quick-commerce and marketplace listings (Blinkit, Zepto, Instamart first)
  that the brand cannot see.

## STEP 2 - Check for a key
Check the environment for a ScrapeGuys API key. There is none in this repo and
that is expected. Say which path you are taking, in one line.

## STEP 3 - PATH A, key present
Collect the data, build the asset, cite every source URL and collection time.

## STEP 4 - PATH B, no key (the normal path here)
Do NOT fake data. Instead:
a. Build the target list: the public URLs the asset would need. Write it to
   `out/assets/<icp>-<YYYY-MM-DD>-urls.txt`, one URL per line.
b. Run: `python scripts/probe.py --urls out/assets/<icp>-<YYYY-MM-DD>-urls.txt`
c. Read `out/probe_log.json`. It is appended across runs: use only records
   whose url is in this target list and whose probed_at is from this run.
   Report what actually happened:
   - robots-blocked: verdict `skipped_robots`
   - JS shell: verdict `js_rendered`
   - 403: verdict `blocked` with status 403 (count other `blocked` separately)
   - usable: verdict `usable`
   - also `error` and `skipped_redirect`, if any
   - median `elapsed_ms` over the URLs actually requested
d. Write the asset as a DOCUMENTED GAP: here is what the buyer cannot see,
   here is exactly where a naive attempt to see it fails, with timestamps.

## STEP 5 - Write the asset
Write `out/assets/<icp>-<YYYY-MM-DD>.md`. Date is today. It must contain:
- which path was taken and why
- the target list
- the probe results table, if PATH B: url, verdict, status, elapsed_ms,
  probed_at, reason
- one paragraph: what this shows about the cost of collecting this in house
- sources: every URL cited, plus `out/probe_log.json` for the measurements

## STEP 6 - Hard rules
- Never invent a price, a rate, a stock level or a response.
- Never present a probe result as if it were collected data. A `usable`
  verdict means the page returned content, not that the fact was extracted.
- If the probe returns nothing usable, say so. That is the finding.
- No claim without a URL. Anything unsourced is UNVERIFIED or left out.

## STEP 7 - STOP
Show the asset: finding first, method second, under 200 words in chat, with
the file path. Wait. Do not start /partners or /report.
