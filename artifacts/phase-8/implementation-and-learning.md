# Phase 8 — Final verification and learning

The [case study](case-study.md) and demo files come from the dosing-skid replay. The video is a narrated-by-caption recap of that replay, with the rendered output PDF. It is not a live browser recording.

## Verification

| Boundary | Observed evidence |
|---|---|
| Customer intake and review | Saved EML and embedded PDF entered through FastAPI. The replay used stubbed extraction and confirmed buyer decisions through the normal endpoints. The regression suite also covered duplicate intake and a one-line customer revision. |
| RFQ and supplier replies | The replay released the approved supplier EML, then imported three separately dated supplier replies using the generated workbook and runtime RFQ reference. |
| Commercial comparison | OMR 42.000 beat OMR 50.000 before the MOQ revision. Revised B cost OMR 30.000. Other cases blocked a wrong-length offer and an expired offer. |
| Historical pricing | The live comparison page showed OMR 0.250 per piece and the source evidence. The first offer showed +40.00%. PostgreSQL tests also covered the 50 mm to 55 mm exclusion and lookup failure. |
| Quote review and release | Changing the selected terms blocked the older approved package. A separate case advanced the clock after approval and verified that release was blocked after expiry. The released PDF was rendered for visual review and matched the EML attachment. |
| Issuance and purchase | The replay recorded manual issuance and separate purchase evidence. The confirmed purchase appeared in sourcing history. |

**Regular suite:** 17 passed with fresh PostgreSQL and pgvector. Three opt-in live tests skipped in that run. **Capture replay:** 1 passed.

**Separate live DeepSeek rerun:** 1 of 3 cleared the complete check. Dosing skid matched the checked values and still needed specification and unit evidence review. Guard rail returned `Item 4` where the answer key expected `4`. Buyer review remains part of the demo workflow. This small sample does not estimate production accuracy.

## What we learned

- **Replay one case across the handoffs.** Separate tests can show that pricing and history work independently. The dosing-skid case shows that a new offer, its benchmark, and the selected cost can coexist on the same line and change which quote is releasable.
- **Test expiry at release time.** Passing approval proves the supplier terms were valid then. A customer-facing file needs another check when it is released.
- **Keep model evidence and commercial correctness separate.** Stubbing extraction makes the business workflow repeatable. The live check shows formatting and evidence issues that the buyer needs to resolve before sourcing.
- **Label the boundaries.** Issuance is staff attestation. Gmail delivery, a live n8n import, and authenticated production approvals were outside verification.

## Reproduce

With a disposable PostgreSQL database and pgvector enabled, set `DATABASE_URL` and run `.venv/bin/python -m pytest -q`. To capture a fresh copy of the demo files:

```sh
PORTFOLIO_CAPTURE_DIR=/tmp/enquiry-demo .venv/bin/python -m pytest -q -s \
  tests/test_workflow_evaluation.py -k 'workflow and dosing-skid and not live'
```
