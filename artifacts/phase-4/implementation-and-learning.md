# Phase 4 — Supplier offer comparison

The buyer moves from an approved RFQ to a traceable supplier choice. The comparison shows eligible offers and blockers. Phase 5 receives a current selection with exact cost and delivery terms.

## 4.1 — Receive and link

Upload an EML at **Supplier replies**, accessible from an approved RFQ's comparison. Python retains the original email, deduplicates by message ID or content hash, and uses the subject reference to find the approved RFQ. It validates the sender against the RFQ's stored recipient addresses and requires both workbook keys to agree. A failed check is visible in the reply inbox. This preserves the evidence without overwriting a valid offer.

An alternative is fuzzy description matching. It helps when identifiers are absent but can attach a reply to the wrong length or revision. Exact identifiers are already available in the package, so they are the stronger link. The cost is manual follow-up when a supplier drops or changes them. Sender matching associates the uploaded reply with a recorded address and assumes the buyer has a trustworthy source mailbox.

## 4.2 — Read and verify terms

Openpyxl reads the existing Supplier offer sheet by label. Stored cell values and coordinates let the buyer verify the price and terms. Formula cells, missing required fields, incompatible specs, and ambiguous pack sizes block eligibility. Matching checks the demo family, grade, and metric dimensions. Buyer review can accept a brand or substitution condition when the underlying checked specs still match.

An LLM could interpret unfamiliar formats, but the template gives us a predictable structure and reproducible checks. The trade-off is that unrecognised layouts, specification vocabulary, and date formats need clarification. Workbooks remain the structured source of truth.

## 4.3 — Compare fulfilment costs

Python uses Decimal and converts both price and minimum quantity to pieces. It takes the greater of demand and MOQ, rounds up to the pack multiple, and prices that purchase quantity. Only eligible offers are ranked by total spend, then earlier delivery. The app uses the current clock for expiry. Tests use a fixed clock.

A's OMR 0.420 per piece costs OMR 210.000 for 500. B's OMR 3.400 per box is cheaper per piece, but an MOQ of 100 boxes costs OMR 340.000. A revision to 50 boxes brings B to OMR 170.000. Sorting by unit price would miss the cost of buying surplus. Charging the surplus to this job is an explicit demo policy and could change in a business that credits reusable inventory.

## 4.4 — Preserve revisions and handle follow-ups

Each linked workbook creates a separate reply record. Comparison uses the newest terms by email time for each invited supplier. An incomplete replacement workbook can block the newer offer without inheriting previous terms. A linked text-only follow-up is shown for buyer review. The buyer can record a hold or withdrawal with a reason. A later valid workbook can supersede it. Earlier RFQs retain their replies but stop driving the current comparison when the requirement or recipient approval changes.

Automatically treating every follow-up as a withdrawal would reduce clicks and could incorrectly suppress valid prices. The manual decision makes the business meaning explicit. The review action and reason are stored on the reply, so this version keeps the latest review action per reply. [Historical benchmark template](historical-benchmark-template.md) specifies the deferred history work.

## 4.5 — Select an offer and hand off to quotation

The comparison shows raw terms, cell evidence, cost and blockers. The buyer selects an eligible reply and explains a departure from the recommendation. A token covers the RFQ and comparison state. The enquiry lock serializes selection with reply import and requirement changes. Phase 5 can read the current line, RFQ reference, selected reply, and revalidated cost, delivery, and validity from the handoff endpoint. An expired or superseded selection returns a conflict.

Automatically selecting the recommendation would be faster. Explicit selection retains the buyer's judgment and ties it to a specific offer. The extra action is worthwhile because the selection may later support a customer-facing promise.

## Verification

The PostgreSQL integration test uses actual EML and workbook fixtures, with supplier references remapped to the generated RFQ and model extraction stubbed. It checks repeat import, approval and selection, the handoff cost, and rejection after a customer revision. Separate fixture tests cover the original and revised MOQ totals and missing pack size. Native mail delivery, unfamiliar workbook formats, and the historical benchmark are outside this verification.
