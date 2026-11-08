# Phase 3.3 — Supplier selection

## Walk through the purchasing decision

1. Confirm shutdown line 10 for the A2-70 stainless hex bolt. Open **Supplier selection and history**. The alias matcher recognises “hex head bolt” and normalises “A2 70” or “A2-70” to the same grade. The directory lookup matches the pair `HEX_BOLT / A2-70`, suggesting A and B.
2. Confirm line 20 for class 10.9. C is suggested because it has that exact coverage row. A's 8.8 coverage is a different grade. The buyer can still add A and record “Can source on request.” The reason stays with the approval. The RFQ fixture therefore has A and C as recipients even though the rule suggests C alone.
3. Keep line 30 awaiting clarification. The page shows its status and the approval endpoint rejects attempts to approve it. Once confirmed as an A2 lock nut, it can match A's `LOCK_NUT / A2` coverage.
4. Apply the customer's change to line 10 from M10 × 50 to M10 × 55. The old approval stays in history, but the line needs confirmation and a fresh supplier approval. The same A/B coverage can still apply. Line 20 keeps its approval.

## Why these boundaries matter

- **Classify first, then match.** Small regex alias lists produce a product family and grade. Exact pair matching then checks the local coverage CSV. A missing or ambiguous classification needs a buyer choice. This keeps the suggestion explainable without asking a model to infer a supplier's capabilities from its name.
- **Coverage is a reason to ask.** The directory covers families and grades. It cannot tell us who has the exact dimensions or quantity in stock. Those requirements stay on the confirmed line for the RFQ. Price, minimum order, and delivery are evaluated when the supplier responds.
- **Store the approved addresses.** PostgreSQL records supplier IDs, addresses, classification, and override reason together. Phase 3.4 can use the readiness helper to retrieve that snapshot only for a confirmed line with a current requirement and unchanged approved addresses.
- **Check the line and the form separately.** The approval is tied to a fingerprint of the confirmed line, including its requirement version. A form token also incorporates directory data and the latest approval ID. A buyer returning to an old tab must reload if any of those changed. The enquiry row lock serializes writes. An exact retry of an approval can return success without appending another record.
- **Preserve decisions on unrelated lines.** The requirement version changes on the line that was reviewed or revised. Approving or revising another line leaves the first line's approval usable. This is the difference between tracking the whole enquiry for history and checking readiness per item.

## Verification and limits

The five-test suite passed with a disposable PostgreSQL database. The shutdown integration test uses saved emails and PDFs with stubbed extraction. It verifies blocked-line approval, the class 10.9 suggestion, a required override reason, exact replay without another approval, stale form rejection, and the unaffected line's continued readiness. The matching vocabulary and coverage data are scoped to the demo directory. Supplier availability and RFQ generation are handled in later phases.
