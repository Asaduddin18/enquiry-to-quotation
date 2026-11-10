# Phase 7 — Historical item prices

## Baseline first

Commit `afc04be` freezes 60 synthetic legacy records, four development cases, and eight held-out cases before feature code. The answer keys name the expected purchase IDs and price flag. The corpus includes past offers and selling quotes, unverified specs, wrong lengths and grades, missing pack sizes, old purchases, and small orders. It uses a small fastener vocabulary and does not estimate production retrieval quality.

| Retrieval at budget 25 | Development gold IDs | Held-out gold IDs |
|---|---:|---:|
| Literal description equality | 4/12 | 2/9 |
| Structured verified-spec lookup | 12/12 | 9/9 |
| Structured plus pgvector | 12/12 | 9/9 |

Counts are purchase-ID occurrences across queries. The product baseline had no benchmark. The final tests verified the exact accepted ID sets and expected flags across all 12 cases. Vector retrieval added no eligible purchases in this sample. It gave the buyer nearby rejected records with an explanation.

## Ingestion and provenance

The local FastAPI import endpoint validates a batch and uses a namespaced purchase-line identifier to upsert legacy rows. Replays preserve the row count, and corrections replace the row for that identifier. Phase 5 purchases are read directly, so recording a real purchase requires no second import. Its actual delivered cost is divided by the actual pieces purchased. The evidence link resolves back to the imported row or native purchase details.

The included n8n subworkflow forwards a batch of reviewed records to the same endpoint. Keeping validation and writes in Python avoids two implementations of the contract. The HTTP endpoint was verified with PostgreSQL. The n8n export was checked as JSON and has not been run in an n8n instance. A caller supplies one item containing a `records` array and configures the app URL. This is for the local demo.

## Retrieval, eligibility and arithmetic

Verified family, dimensions, and grade give structured matches first priority. pgvector fills the remaining candidate budget with cosine-ranked, alias-normalised character trigram vectors. This lexical embedding requires no model download and handles some spelling and formatting variation. It is weaker on unseen synonyms than a learned embedding. With pgvector disabled the app still uses structured matches. Candidate caps and synthetic coverage limit recall claims.

Python checks record type, verified spec, delivered OMR basis, known pack size, date and purchase quantity. Default windows are 12 calendar months and 0.5× to 2× the quantity the trader must actually buy. The current 500-piece request with an MOQ of 1,000 uses the 1,000-piece basis. The demo matcher withholds a benchmark when it detects unsupported mandatory constraints, such as a standard or substitution condition. Rich verified brand and standard fields remain a limitation.

A box of ten at OMR 3.200 contributes OMR 0.320 per piece. With two other purchases at 0.300 and 0.330, the median is 0.320. An offer of 0.420 is 31.25% higher and triggers a price check. Exactly 25% stays unflagged. After changing the requested length to 55 mm, the three 50 mm records contribute zero observations. The 55 mm fixture has only one eligible purchase, so the median is withheld.

## Buyer outcome and verification

The offer page displays the current purchase basis, sample count, median, difference, source links, and reasons retrieved candidates were excluded. Insufficient history and a database lookup failure have different statuses. A flag provides evidence for review and does not change live offer eligibility or ranking.

The suite passed **17 tests** against a disposable PostgreSQL database with pgvector. Three opt-in DeepSeek checks from Phase 6 were skipped. The history tests cover repeat import, correction, 12 frozen cases, and a simulated lookup failure. The existing workflow test now verifies that a confirmed purchase appears on the live offer page with its evidence link.

## Reproduce

- Enable pgvector in a disposable database with `CREATE EXTENSION vector;`. Omit it to use structured-only retrieval.
- Set `DATABASE_URL` and run `.venv/bin/python -m pytest -q`.
- With the app running locally, import the example corpus using `curl -H 'Content-Type: application/json' --data-binary @artifacts/phase-7/history.json http://127.0.0.1:8000/history/import`.
- Optional policy settings are `HISTORY_LOOKBACK_MONTHS`, `HISTORY_QUANTITY_MIN`, and `HISTORY_QUANTITY_MAX`. The defaults are 12, 0.5, and 2.
