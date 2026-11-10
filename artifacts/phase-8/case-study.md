# From supplier emails to a defensible customer quote

**Self-directed portfolio project using synthetic data.** Inspired by a [public Upwork brief for a trading-company enquiry and quotation workflow](https://www.upwork.com/freelance-jobs/apply/automation-full-enquiry-quotation-workflow-for-trading-company-Gmail-Sheets-LLM_~022111785546774371094).

## The purchasing problem

A Muscat distributor receives an enquiry for 120 stainless hex bolts. Its buyer must confirm the specification, request prices from suppliers, and decide which offer supports a customer promise. The cheapest price per piece can require a bigger purchase than the job needs. A supplier can revise its terms after an internal quote has already been approved.

## The recorded walkthrough

[Watch the 45-second replay recap](demo/walkthrough.mp4). It uses observed replay results and shows the actual generated PDF on the final frame.

1. Open the [customer email](demo/customer-enquiry.eml) and [requirement PDF](demo/customer-requirement.pdf). The buyer confirms M8 × 35 A2-70 and 120 pieces.
2. Inspect the [approved supplier RFQ](demo/approved-rfq.eml). It contains the Excel template, approved recipients in BCC, and an opaque reference.
3. Follow the offers in arrival order. The app links each workbook by RFQ reference and supplier sender. Three past purchases give a median of OMR 0.250 per piece.

| Offer | OMR per piece | Pieces to buy | Delivered cost |
|---|---:|---:|---:|
| [A, first reply](demo/supplier-reply-1.eml) | 0.350 | 120 | 42.000 |
| [B, original minimum](demo/supplier-reply-2.eml) | 0.250 | 200 | 50.000 |
| [B, revised minimum](demo/supplier-reply-3.eml) | 0.250 | 120 | 30.000 |

4. A wins initially on total spend. Its unit price is 40% above the historical median, which prompts a price check. B's revised minimum brings its total below A's. The buyer selects B, and the app blocks release of the earlier approved quote.
5. Open the [released customer PDF](demo/approved-quotation.pdf) and [approved email draft](demo/approved-quotation.eml). The 20% target margin yields OMR 0.313 per piece after rounding, or **OMR 37.560 excluding VAT**. The test verified that the PDF bytes match the email attachment. It then recorded staff issuance and a separate purchase entry.

## What the project demonstrates

The quote can be traced back to the confirmed requirement, approved recipients, supplier reply, delivered cost, and customer-facing package. Price and eligibility are calculated in Python. AI proposes enquiry fields for staff review. PostgreSQL stores the decisions and preserves the evidence used at each handoff.

See the [verification and learning report](implementation-and-learning.md) for the exact test scope and remaining limits.
