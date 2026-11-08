# Phase 3.2 — Buyer review and customer revisions

| Business outcome | Implementation and learning |
|---|---|
| Correct requirements before sourcing | Buyers can confirm individual lines or mark them awaiting clarification. Changes require a reason, and the original extraction remains available. Keeping source data separate from buyer decisions makes the decision traceable. |
| Link a change to the original enquiry | Reply headers or a matching sender and customer reference suggest a parent. The buyer previews the link and checks the affected line numbers before applying it. An item number identifies a line within its enquiry. |
| Preserve work on unaffected lines | Applying a revision keeps the changed line's stable ID and returns it to review. Other line decisions carry forward. Readiness belongs at line level because different items can move independently. |
| Protect decisions from duplicates and stale tabs | PostgreSQL stores versioned snapshots. A repeated revision applies once, and an older review form cannot overwrite a newer decision. Replay protection and version checks address different failure modes. |

## Walkthrough

Import the shutdown enquiry and use **Buyer decisions** to review its lines. Import `16-customer-revision.eml`, preview the suggested original enquiry, and confirm the listed-line scope. Line 10 changes from M10 × 50 to M10 × 55 and returns to review. Lines 20 and 30 keep their decisions.

## Verification and scope

All five tests passed with a disposable PostgreSQL database. The revision test uses the original EML and embedded PDFs with stubbed model output. It verifies validation, correction reasons, linking, selective reopening, replay, and stale review rejection. The live revision extraction was not verified. The implemented path covers changes to existing numbered lines with unchanged shared terms. Whole-document replacements and shared-term edits require separate handling.
