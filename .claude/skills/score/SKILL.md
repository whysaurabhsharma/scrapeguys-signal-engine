---
name: score
description: Run the scoring script and interrogate the resulting ranking. Use when asked to score, rank, tier or re-rank accounts.
allowed-tools: Read, Bash(python scripts/*)
---

# /score

Follow these steps in order. Do not skip, merge or reorder them.
This skill reads and reports. It never edits a CSV and never sends anything.

## STEP 1 - Run the scorer

Run `python scripts/score.py --asof <today>` (YYYY-MM-DD).
Report the tier counts (A, B, nurture, reject) from the script's summary.

## STEP 2 - Show the top 10

Read `data/scored.csv`. Show the top 10 as a table: company, icp, score,
tier, pain, freshest_days, reason. Copy values exactly; do not round or reorder.

## STEP 3 - Interrogate the ranking

Answer in plain English, each in two sentences or fewer, citing signal URLs
from `data/signals.csv`. If the evidence does not support an answer, say so.

1. Which account would you call first, and does the ranking agree?
2. Is any Tier A account there on weak evidence? Name it and say why.
3. Is any account ranked lower than it deserves? Name it and say why.

## STEP 4 - If the ranking looks wrong, propose weights

You may NOT change a score, a tier or an id, or edit any CSV. Propose a change
to the WEIGHTS in `scripts/common.py` (`SIGNAL_MODEL`, `DATE_CONFIDENCE`,
`CONFIDENCE`, `STAGES`). `TIERS` is fixed and never part of a proposal.

For each change state: constant and key, current value, proposed value, and
which accounts would move from which tier to which. Then STOP and wait for
approval. Do not edit `common.py`. The human edits it, then re-run STEP 1.

## STEP 5 - Golden check

For each row in `tests/golden.csv` whose `domain` matches the normalised
domain of a `website` in `data/scored.csv`, check:
- `buy` must score Tier A or B.
- `no` must score nurture or reject.

Report matched/total. Print every mismatch: domain, expected label, tier it
got, and the reason from `scored.csv`.

Tuning the weights until golden passes is overfitting. Golden is a check on
the model, not a target for it. If a weight change is proposed after seeing a
golden mismatch, the proposal must say so explicitly: which mismatch prompted
it, and why the change is justified on the merits rather than to make the
test pass.
