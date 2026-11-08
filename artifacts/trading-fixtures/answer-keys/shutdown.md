# Shutdown practice case

| Event | Expected result |
|---|---|
| 01 | Extract three lines from the PDF. Quote by 9 Nov at 11:00 GST. Deliver by 12 Nov at 14:00 GST. Partial coverage is allowed for lines 10 and 20. |
| 02–04 | One RFQ per line and revision. Invite A/B, A/C, and A respectively. Supplier documents exclude customer identity and reference. |
| 05 | A qualifies for line 10 at OMR 210.000. Flag its unit price, 31.25% above the OMR 0.320 confirmed-purchase median. P04 has the wrong length. O01 and Q01 represent different evidence types. |
| 06 | B costs OMR 0.340 per piece but requires 1,000 pieces. A still wins at OMR 210.000 versus OMR 340.000. |
| 07 | A's line 20 reply links correctly. Class 8.8 fails the requirement. |
| 08 | C qualifies at OMR 100.000. The potential partial quote is OMR 387.500 at 20% gross margin. |
| 09 | Hold line 30 for brand approval. Keep it pending on the partial quote. |
| 10 | B's revised minimum of 500 pieces costs OMR 170.000. Recommend B and reopen the draft. Updated partial quote is OMR 337.500. |
| 11 | Latest B offer is missing pack size. Hold it for clarification and flag the quote for review. Do not combine the old pack size with the new offer. |
| 12 | C mentions a replacement sheet but sends none. Request the sheet and flag C's existing offer for review before relying on it. |
| 13 | Sender is outside the invited supplier list. Route for review without changing a supplier offer. |
| 14 | B confirms ten pieces per box. The latest offer costs OMR 165.000. |
| 15 | Customer declines the alternative brand and confirms partial coverage. |
| 16 | Reopen line 10 for M10 x 55. Prior line 10 offers stay attached to Rev 0. Line 20 keeps its existing review status. |
| 17 | Subject identifies line 10, but attachment identifies line 20. Hold as a mismatch. |
| 18 | C's prior terms have expired and new availability misses the required date. Line 20 cannot support a quote without fresh terms. |
| Duplicate replay | Keep one copy of the message and do not add another offer revision. |

No customer quote is issued and no actual purchase is confirmed in this trail. Supplier replies can contribute offer history once validated.
