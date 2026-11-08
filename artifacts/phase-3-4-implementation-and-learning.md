# Phase 3.4 — Supplier-ready RFQ packages

**Business outcome.** A buyer can take a confirmed enquiry line and its approved recipients, inspect the exact supplier-facing files, and approve a package for manual sending.

## Walkthrough

1. Import the shutdown enquiry. Review the source and confirm line 10 for the M10 × 50 A2-70 bolts. Approve A and B as recipients.
2. On the supplier selection page, open **Prepare or review RFQ package**. Generate the package and inspect its subject, body, BCC list, and Excel workbook. The request uses an opaque reference that appears in the subject, body, and workbook. The workbook also uses that reference as its supplier-facing line key because each package covers exactly one line.
3. Review the buying terms and template before approving. The workbook carries the item, quantity, unit, delivery deadline, and blank supplier fields for the offer. Once approved, download the EML for manual sending. The workbook embedded in that email is byte-for-byte the one reviewed.
4. Apply the customer's change to line 10. The old package is retained in PostgreSQL, but the current workflow blocks its download. Confirm the revised requirement and approve recipients again to create a new package. An unaffected line can keep its package.

## Design decisions and what they teach

| Decision | Business reason and implementation |
|---|---|
| Gate preparation on current recipient approval | The application checks the confirmed line and the exact approved addresses before preparing or releasing a package. An older selection cannot authorize outreach for a revised item. |
| Generate once per recipient approval | PostgreSQL stores a single immutable EML and workbook pair per approval. Refreshes and repeated preparation return the same reference. The enquiry lock serializes changes to line and recipient state during preparation and approval. |
| Approve the stored files | The approval request names the exact package reference and records an approval timestamp. This gives the buyer a way to prove what was reviewed even if data or templates change later. |
| Publish only purchasing fields | The builder uses the confirmed item fields, deadline, and approved recipients. It does not copy customer messages, attachments, or selling prices. A check catches the known customer reference and sender details in item text. The buyer must still review free-text fields for sensitive information. |
| Carry the reference across the handoff | A returned Excel attachment can carry the same RFQ key that appears in the email subject. Phase 4 can use that key and sender to link replies without inferring identity from the product description. |

## Verification and boundaries

All five tests passed with PostgreSQL. The shutdown integration test uses the actual enquiry and revision emails with stubbed model extraction. It verified blocked preparation for an unresolved line, repeat preparation and approval, blocked EML download before approval, matching BCC recipients, the opaque reference in both formats, and byte-for-byte equality between the workbook preview and the EML attachment. It also verified that the revised line's old EML was blocked while the unaffected line's workbook remained accessible.

The workbook was inspected as XLSX package contents. Native Excel rendering and email-client sending were outside this verification. A download cannot be recalled once it leaves the app. Phase 3 covers local intake through manual-send handoff. Gmail integration and supplier reply processing belong to later work.
