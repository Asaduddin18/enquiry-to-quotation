# Enquiry to Quotation

A freelance portfolio project for a fictional B2B trading company. Turn a customer enquiry into a reviewed quotation backed by supplier offers.

## First milestone

1. Read a Gmail enquiry or accept a typed PDF, Excel file, or pasted text. Extract item descriptions, specifications, quantities, and units with DeepSeek.
2. Review the lines, categories, and suppliers in Google Sheets. Prepare category-specific Gmail RFQ drafts and Excel reply templates. Keep customer identity, customer references, and selling prices out of supplier-facing materials.
3. Match supplier replies to RFQ references and line numbers. Compare price, unit, minimum quantity, lead time, and validity.
4. Apply margin rules, route exceptions for approval, and prepare a quotation PDF and customer email draft. Use PostgreSQL to track revisions, approvals, and drafts.

Start with one mailbox, one currency, fixed categories, and synthetic data. Staff send emails manually.

## Follow-up milestones

1. **Historical sourcing search.** Surface past purchases and quotes for similar items. Check critical specifications and show the original record. Historical prices are benchmarks that need current confirmation.
2. **Supplier follow-up and quote readiness.** Track missing or expired offers by line and prepare reminders for outstanding items after staff confirm the RFQ was sent.

## Status

Repository scaffold. The workflow and integrations are planned.

[Original portfolio brief](https://github.com/Asaduddin18/ai-freelance-playbook/tree/main/projects/02-enquiry-quotation)

[Phase-wise portfolio plan](artifacts/phase-wise-plan.md)

## Run the Phase 3.1 review app

Use Python 3.12 and a local PostgreSQL database. Install dependencies into a virtual environment, then set `DATABASE_URL` and `DEEPSEEK_API_KEY` locally. `DEEPSEEK_MODEL` is optional.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
set -a
source .env
set +a
.venv/bin/uvicorn enquiry.app:app
```

Open http://127.0.0.1:8000 and upload the shutdown case's `01-customer-enquiry.eml`. Use `.venv/bin/python -m pytest` for the tests. Set `DATABASE_URL` to a disposable database to include the PostgreSQL test.

- [Phase 3 implementation plan](artifacts/phase-3-implementation-plan.md)
- [Phase 3.1 implementation and learning report](artifacts/phase-3-1-implementation-and-learning.md)

[Phase 3.2 implementation and learning report](artifacts/phase-3-2-implementation-and-learning.md)

[Phase 3.3 implementation and learning report](artifacts/phase-3-3-implementation-and-learning.md)

[Phase 3.4 implementation and learning report](artifacts/phase-3-4-implementation-and-learning.md)

[Phase 4 implementation and learning report](artifacts/phase-4/implementation-and-learning.md)

[Phase 5 implementation and learning report](artifacts/phase-5/implementation-and-learning.md)
