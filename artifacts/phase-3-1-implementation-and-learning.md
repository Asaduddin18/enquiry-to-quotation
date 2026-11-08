# Phase 3.1 — Implementation and learning

| Business outcome | Implementation | What to learn |
|---|---|---|
| See what the customer actually sent | Import the saved email, extract the embedded PDF, and preserve the original message. | Separate source records from extracted fields so staff can investigate mistakes without reconstructing the inbox. |
| Review usable item details before outreach | Ask DeepSeek for typed candidate fields and source excerpts. Show flagged fields beside the source email and PDF. | An excerpt proves the cited text exists. The buyer still checks whether the proposed field follows from it. |
| Keep quote and delivery promises distinct | Pass the email date in Oman time and request separate deadlines with evidence. | Relative language such as “tomorrow” depends on the original email timestamp, even during replay. |
| Recover without duplicating work | Use a unique message key, save source before extraction, and record each attempt. Serialize processing for the same enquiry with a database row lock. | Intake and extraction have different failure modes. A retriable model failure should leave the source available and produce no duplicate enquiry. |
| Stop before supplier outreach | Display candidate values with a review status. | An extraction can be well formed and still require a commercial decision. Buyer confirmation belongs in 3.2. |

The source PDF, MIME parser, and evidence checks have local tests. The PostgreSQL replay and retry test requires a disposable database. The sandbox prevented starting the local PostgreSQL server, so database-backed acceptance remains open.

A live DeepSeek run on the shutdown fixture returned lines 10, 20, and 30 with quantities 500, 200, and 300 EA. It found the quote deadline of 9 November at 11:00 GST, the delivery deadline of 12 November at 14:00 GST, and permission to quote lines 10 and 20 separately. The evidence checker raised no issues for this fixture. This verifies the model call on one practice example. Three local tests passed and the PostgreSQL test was skipped.
