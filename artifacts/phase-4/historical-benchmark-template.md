# Historical benchmark template

**Status.** Scheduled for [Phase 7](../phase-wise-plan.md#phase-7--check-historical-item-prices). The live comparison reports that the historical benchmark is pending.

- **Input:** confirmed requirement version, family, dimensions, grade, mandatory standard or brand, requested quantity, current delivered OMR per piece, and evaluation date.
- **History record:** stable source ID, record type, original description, verified specs, purchase date, quantity, unit, pack size, OMR cost basis, and source reference.
- **Loading:** n8n validates and upserts records by source ID. Refresh embeddings when the description changes.
- **Retrieval:** union pgvector description candidates with structured exact matches. Deduplicate by source ID.
- **Eligibility:** Python checks exact critical specs, confirmed-purchase status, delivered OMR basis, known pack conversion, and configured date and quantity windows. Values for those windows remain a business decision.
- **Output:** benchmark status, median OMR per piece, percentage difference, and the eligible source records. At least three comparable purchases are required. Flag differences greater than 25% in either direction.
- **Failure states:** distinguish insufficient comparable purchases from an unavailable history store. Live offer comparison remains available.
- **Acceptance:** M10 × 50 purchases at 0.300, 0.320 and 0.330 yield a median of 0.320 and a 31.25% flag for 0.420. After the customer revises to M10 × 55, those 50 mm records contribute zero benchmark observations. Supplier offers and customer quotes remain separately labelled context.
- **Display:** render the evidence with a fixed template first. A generated explanation can be added after retrieval and arithmetic are verified.
