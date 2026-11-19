---
paths:
  - "data/**"
---

# Data contract

accounts.csv, signals.csv and scored.csv are written ONLY by scripts.
Never edit them directly, with Write, Edit, or a shell redirect.

New data is written as a JSON list to data/staging/ and passed to
scripts/ingest.py. Copy the shape in data/staging/EXAMPLE.json exactly.

account_id and signal_id are derived by the script from the normalised
domain. Never supply an id by hand; invented ids collide.

signal_date is the date the event happened, from the source page or API.
Never today. An undated signal is dropped, not estimated.
captured_at is when you found it. Decay runs on signal_date.

A signal without an http evidence_url is rejected.
A named decision maker without a public source URL is rejected.
A domain in config/suppress.csv is rejected.
An account with no valid signal is rejected.

Read every REJECTED line from ingest and fix the research,
not the record.
