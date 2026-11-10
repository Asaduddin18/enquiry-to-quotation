# Phase 6 — Workflow evaluation

The three cases below were written after Phase 5 and kept separate from the original shutdown practice trail. The case file records expected outcomes. The runner generates customer EML/PDF files and returns filled copies of the workbook produced by the application, using the actual RFQ reference. Tests submit the files through FastAPI and use a disposable PostgreSQL database.

| Case | Business decision | Observed result |
|---|---|---|
| Pump base | An M16 × 70 offer cannot fulfil an M16 × 75 request even if the supplier and grade are right. | Wrong length blocked. Corrected offer cost OMR 48.000 and produced an OMR 60.000 quotation. |
| Dosing skid | Compare total spend and reopen the quote when the buyer switches to a revised offer. | A cost OMR 42.000. B originally cost OMR 50.000 despite its lower unit price. Lower MOQ brought B to OMR 30.000. The old approved quote could no longer be released after selection changed. The new quote total was OMR 37.560. |
| Guard rail | An expired price cannot support a customer promise. | The offer remained visible with an expiry reason. The line had no usable quotation handoff. |

## What the tests establish

- The held-out replay passed **3 of 3 cases**, including two customer packages released and recorded as manually issued, one expired offer blocked, and one wrong-length offer blocked then corrected. The existing regression suite still covers a one-line customer revision, partial quotes, and a manager margin exception.
- Buyer actions and application validation run through the normal endpoints. A fixed clock makes offer expiry reproducible. Workbook attachments come from the generated RFQs, so a reference mismatch between test inputs and runtime packages cannot mask a linkage bug.
- The PostgreSQL replay uses a model stub to isolate commercial logic. A separate opt-in live test checks customer reference, both deadlines, line number, quantity, unit, and evidence warnings. Keep these results separate when discussing model quality.
- OMR 30.000 divided by 0.80 gives OMR 37.500 before unit-price rounding. The application rounds the unit price up to OMR 0.313, so 120 pieces produce OMR 37.560. Testing the displayed total caught the distinction between exact target margin and reproducible unit-price arithmetic.
- The sample contains three short synthetic enquiries using one template. It measures the chosen business cases and does not estimate production accuracy or validate live email delivery.

## Live DeepSeek results

The checked values matched the answer key in **3 of 3 cases**. This covers customer reference, both deadlines, line number, quantity, and unit. **0 of 3 cleared evidence review**, so all three opt-in tests failed the stricter gate.

| Case | Review reason |
|---|---|
| Pump base | The specification citation did not pass the source check. |
| Dosing skid | The model interpreted “complete line” as an unresolved scope conflict even though the attached request listed one item and its quantity. |
| Guard rail | Evidence checks flagged line number, specification, quantity, and unit. |

The workflow should keep buyer review in place. This evaluation exposed both citation gaps and an over-cautious conflict flag. These were recorded as findings, and extraction rules were left unchanged so the results remain interpretable. The run did not independently grade the extracted specification text. A larger, separate evaluation would be needed to measure generalization.

## Reproduce

Run `.venv/bin/python -m pytest -q` with `DATABASE_URL` pointed at a disposable PostgreSQL database. To run live extraction separately, export the existing local DeepSeek configuration and run `RUN_LIVE_EXTRACTION=1 .venv/bin/python -m pytest -q tests/test_workflow_evaluation.py -k live`.
