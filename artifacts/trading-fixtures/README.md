# Trading fixtures

Replay fictional Oman fastener enquiries using local email files. Each numbered EML represents one arrival or outbound message and embeds its own attachments. The adjacent PDF and Excel files are convenience copies. Replay only the EML files in number order. A repeat of any file represents duplicate delivery of the same message.

- [Shutdown practice case](cases/practice/shutdown/) includes the original enquiry, supplier RFQs and returns, commercial revisions, and operational failures.
- [Supplier workbook](templates/supplier-quotation.xlsx) is the reusable blank form. The trader fills the request fields and suppliers complete the offer section.
- [Reference data](reference-data/) contains the invited suppliers and historical purchasing evidence.
- [Answer key](answer-keys/shutdown.md) gives the expected decisions at each step. Keep it separate from workflow inputs.

These synthetic documents follow the email intake, category-based RFQ drafting, and structured supplier reply pattern in the [portfolio brief](https://github.com/Asaduddin18/ai-freelance-playbook/tree/main/projects/02-enquiry-quotation). The fixtures use ordinary message timing, separate attachments, internal RFQ references, and incomplete or conflicting supplier responses. All mailboxes use reserved example addresses. Live Gmail integration belongs at the end.

Extend this folder with held-out cases using different customers, document layouts, items, and prices. Include corrupt or protected workbooks, unclear customer specs, late delivery, conflicting workbook terms, and a below-floor margin approval. Keep their answers separate from replay inputs.
