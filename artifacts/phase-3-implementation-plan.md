# Phase 3 — From customer enquiry to approved supplier RFQ

**Business outcome.** The buyer can turn a saved customer enquiry into supplier-ready requests with confirmed quantities, specifications, deadlines, and recipients. Each approval can be traced to the evidence and to the exact documents reviewed.

## 3.1 — Capture and inspect the enquiry

- Import the original EML and embedded typed PDF. Save the original before asking DeepSeek for candidate requirements.
- Present the original evidence alongside extracted dates, item specifications, quantities, and review issues. Keep quote and delivery deadlines distinct.
- Track imports and extraction attempts in PostgreSQL. Repeat imports resolve to the same case. Extraction failures retain the source for retry.
- **Accept when** the shutdown enquiry opens as three reviewable lines with source evidence and replay produces one enquiry.

## 3.2 — Confirm requirements and manage revisions

- Let the buyer correct individual fields and record why a correction was needed. Require confirmation of critical details before a line can proceed.
- Track revisions separately from the original extraction. When a customer changes one line, reopen that line and preserve the earlier decision history.
- **Accept when** the buyer can confirm the initial shutdown enquiry, then import the M10 x 55 change and see only the affected line reopen.

## 3.3 — Select suppliers for confirmed lines

- Load the local supplier directory and category coverage. Suggest eligible suppliers and show the coverage behind each suggestion.
- Let the buyer add or remove candidates and confirm recipients. Flag lines with no eligible supplier. Historical sourcing can enrich the shortlist when available.
- **Accept when** the buyer can review the A/B, A/C, and A selections for the three shutdown lines and correct a recipient before any draft is approved.

## 3.4 — Generate and approve supplier RFQ packages

- Produce one local email draft and one prefilled Excel template per confirmed line revision. Include an opaque RFQ reference in the subject, body, and workbook. BCC suppliers invited to the same request.
- Build the supplier view from approved purchasing fields. Keep customer identity, customer references, and selling prices out of both files.
- Record approval against the exact draft, workbook, recipients, and requirement revision. Changes require a new review. Replaying approval for the same package preserves one RFQ reference.
- **Accept when** the buyer can inspect and approve the three local RFQ packages and download them for manual sending. Phase 4 uses their references to link returned workbooks.

## Integration boundary

Python owns workflow rules, FastAPI presents the review screens, DeepSeek proposes extraction candidates, and PostgreSQL keeps durable state. Use local fixtures and reference data for Phase 3. Gmail, n8n, and Google Sheets can connect once the local workflow is proven.
