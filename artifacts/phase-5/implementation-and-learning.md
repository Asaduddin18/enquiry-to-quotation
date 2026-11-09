# Phase 5 — Customer quotation

## 5.1 Assemble the quote

Open **Customer quotation workspace** from an enquiry. Select lines with eligible Phase 4 selections and record customer permission for any partial quote. The workspace displays extracted permission as context. The buyer attests that it covers the selected subset.

PostgreSQL stores the exact line versions, supplier replies, fulfilment costs, and terms in a numbered draft. A live-only view would automatically reflect newer offers but would make it hard to prove what the buyer reviewed. A snapshot costs storage and makes changes explicit. The enquiry lock serializes drafting with the upstream mutations.

## 5.2 Price each line

The demo targets 20% gross margin and requires an exception below 15%. For 500 pieces costing OMR 210.000, divide cost by 0.80, then divide by quantity. OMR 0.525 per piece gives OMR 262.500. OMR 0.480 instead gives OMR 240.000 and a 12.5% margin. Overrides require a reason.

Decimal arithmetic rounds the target unit price up to three decimal places before multiplying. This can put the realised margin slightly above target. Pricing the line first could hit the target more closely, but the visible unit price might no longer multiply to the displayed line total. A line-level floor makes discounts visible even when other lines are more profitable.

## 5.3 Keep the promise supportable

The shortest supplier validity caps the quote validity. A buyer can shorten it. Delivery is taken from the eligible supplier offer and each pending line is excluded from price and delivery. Approval and email release recheck the selected offers, requirement versions, and expiry. A stale package keeps its original PDF for audit.

## 5.4 Approve exact files

The internal page shows the cost, margin, and offer evidence. ReportLab builds the customer PDF from the customer-facing fields, and Python embeds the same bytes in the EML. Both are stored when the revision is created. Approval is tied to that immutable revision. For a below-floor price, the demo requires explicit manager attestation and a reason. This is a local workflow control and does not authenticate a manager's identity.

## 5.5 Record what happened

Release makes the approved EML available for manual sending. Staff separately attest that they sent that revision. The timestamp records the staff action and does not verify delivery. If a newer revision is issued, the earlier issued revision displays as superseded. A download already obtained remains usable outside the application.

Purchases are separate entries with an evidence reference, date, actual delivered cost, and pieces bought. Repeating the same entry preserves one record. A conflicting reuse of the same reference for that quote line is rejected. This separation keeps customer selling prices out of future purchase-cost benchmarks.

## 5.6 Verification

The PostgreSQL integration test follows the shutdown fixtures from intake and sourcing through a partial quote, manager exception, exact PDF attachment, issuance, and separately recorded purchase. It checks that a customer revision blocks release of the stale draft and preserves the issued PDF. Pricing tests independently verify the OMR 387.500 and 337.500 scenarios and the rounding policy. Fixture extraction is stubbed and the clock is fixed. The generated PDF was reopened and its text inspected in the test. Native mail delivery and production approval permissions were outside verification.
