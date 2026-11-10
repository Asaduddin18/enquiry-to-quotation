# Enquiry to Quotation

A freelance portfolio project for a fictional B2B trading company. Turn a customer enquiry into a reviewed quotation backed by supplier offers.

## Portfolio walkthrough

Start with the [case study and recorded demo](artifacts/phase-8/case-study.md). The local app takes a saved customer enquiry through buyer review, supplier RFQs, Excel offer comparison, historical price checks, and an approved customer quotation.

The demo uses synthetic Oman trading data and OMR. Staff send approved emails manually and record issuance. The [final verification report](artifacts/phase-8/implementation-and-learning.md) lists the tested boundaries.

[Original portfolio brief](https://github.com/Asaduddin18/ai-freelance-playbook/tree/main/projects/02-enquiry-quotation)

[Phase-wise portfolio plan](artifacts/phase-wise-plan.md)

## Run the local app

Use Python 3.12 and a local PostgreSQL database. Install dependencies into a virtual environment, then set `DATABASE_URL` and `DEEPSEEK_API_KEY` locally. `DEEPSEEK_MODEL` is optional.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
set -a
source .env
set +a
.venv/bin/uvicorn enquiry.app:app
```

Open http://127.0.0.1:8000 and upload the shutdown case's `01-customer-enquiry.eml`. Use `.venv/bin/python -m pytest` for the tests. Set `DATABASE_URL` to a disposable database to include PostgreSQL integration tests. Enable pgvector in that database to exercise vector retrieval.

- [Phase 3 implementation plan](artifacts/phase-3-implementation-plan.md)
- [Phase 3.1 implementation and learning report](artifacts/phase-3-1-implementation-and-learning.md)

[Phase 3.2 implementation and learning report](artifacts/phase-3-2-implementation-and-learning.md)

[Phase 3.3 implementation and learning report](artifacts/phase-3-3-implementation-and-learning.md)

[Phase 3.4 implementation and learning report](artifacts/phase-3-4-implementation-and-learning.md)

[Phase 4 implementation and learning report](artifacts/phase-4/implementation-and-learning.md)

[Phase 5 implementation and learning report](artifacts/phase-5/implementation-and-learning.md)

[Phase 6 evaluation and learning report](artifacts/phase-6/implementation-and-learning.md)

[Phase 7 historical pricing evaluation and learning report](artifacts/phase-7/implementation-and-learning.md)
