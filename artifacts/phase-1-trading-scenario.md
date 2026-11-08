# Phase 1 — Trading scenario

All companies, offers, historical prices, and policy thresholds are fictional. The workflow draws on the [public Upwork brief](https://www.upwork.com/freelance-jobs/apply/automation-full-enquiry-quotation-workflow-for-trading-company-Gmail-Sheets-LLM_~022111785546774371094).

## Business setup

- A Muscat fastener distributor sources to order from three Oman-based suppliers for an Oman factory maintenance team. All prices are in OMR and include delivery to the customer's site in Muscat.
- The customer emails a typed requirement PDF. The buyer checks the enquiry, contacts suppliers, and proposes a quote. A separate approver reviews commercial exceptions and approves the quote. Staff send emails manually.
- Supplier A covers common fasteners, B sells bulk packs, and C specialises in higher-grade items. The buyer uses product coverage and past purchases to shortlist suppliers.

## Decision rules

- Confirm item, dimensions, material, grade, quantity, and unit. Keep the quote deadline separate from the required delivery date. Clarify missing critical details before sourcing.
- Send one RFQ per enquiry line with an opaque reference tied to the requirement revision. BCC invited suppliers on identical requests. Exclude the customer's identity, internal references, and selling prices.
- Link replies by RFQ reference and supplier sender. Route unresolved replies to the buyer. Check offered specs separately and retain prior versions when an offer changes.
- Require the confirmed spec, valid price, known pack size where relevant, and delivery within the customer's window. Hold brand or origin exceptions for approval when the requirement calls for it.
- Compare delivered OMR per piece and total spend for the required purchase quantity. Round up to satisfy whole packs and minimum quantities. Charge unavoidable surplus to the current job.
- Recommend the eligible offer with the lowest total spend. Break ties by earlier delivery. Mark the line blocked if no offer qualifies.
- Use a 20% target gross margin and require exception approval below 15%. At target margin, divide total buy cost by 0.80. The customer quote expires by the earliest expiry of its supporting offers.
- Quote a subset only if the customer accepts partial coverage. List pending lines. Recheck unsent quotes when supporting offers change. Retain issued quotes as sent.
- Keep supplier offers, issued customer quotations, and confirmed purchases distinct. Search historical descriptions for similar items and verify critical specs. Flag a current cost more than 25% above or below the median of at least three comparable confirmed purchases.

## Main demo case

The factory needs a quote by tomorrow and delivery within five business days. All listed prices are valid at review time.

| Line | Requirement | Offers and expected decision |
|---|---|---|
| 10 | 500 M10 × 50 A2-70 stainless hex bolts | A offers OMR 0.420 each, minimum 500, in three days. B offers OMR 3.400 per box of ten, minimum 100 boxes, in four days. Both meet the spec. Choose A at OMR 210.000 total versus B at OMR 340.000. Quote OMR 262.500 at target margin. |
| 20 | 200 M12 × 60 class 10.9 hex bolts | A offers class 8.8 at OMR 0.350 each. C offers class 10.9 at OMR 0.500 each, minimum 200, in four days. Choose C at OMR 100.000 total and quote OMR 125.000. |
| 30 | 300 M10 stainless locking nuts, alternatives subject to customer approval | A offers a substitute brand that meets the required spec. Hold the line pending approval. If the customer accepts partial coverage, quote lines 10 and 20 at OMR 387.500 total and list line 30 as pending. |

## Cases for Phase 2

- **Supplier revision.** B lowers the minimum to 50 boxes and retains its other terms. Spend drops to OMR 170.000. Recommend B and reopen the unsent quote for review.
- **Historical match.** Match alternate wording for the same M10 × 50 A2-70 bolt. Exclude M10 × 55 from the benchmark.
- **Price anomaly.** Comparable purchases at OMR 0.300, 0.320, and 0.330 per piece put the OMR 0.420 offer about 31% above the median. Flag it for review.
- **Offer expiry.** Request reconfirmation or select another valid offer. Keep the expired offer visible in history.
- **Customer revision.** If the customer changes line 10 to M10 × 55, reopen sourcing for that line. Preserve the earlier offers against the earlier requirement.
- **Margin exception.** A selling price of OMR 240.000 against a cost of OMR 210.000 yields a 12.5% margin. Route it for approval.
