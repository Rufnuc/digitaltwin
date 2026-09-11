# Data ingestion (Phase 1 foundation + roadmap)

## Now (Phase 1)

- **Demo seeding** — `python -m app.seed.demo_data [--reset]` generates a
  deterministic, internally consistent 24-month dataset, every row tagged `DEMO`.
- **API entry** — records created through the API are `REAL` and audit-logged.
- **Invoice validation** — on create, line arithmetic is checked
  (`quantity × unit_price == line_total`, subtotal/total recomputed); failures
  flag `NEEDS_REVIEW` rather than being corrected.
- **Provenance tables** — `data_sources`, `data_imports`, `documents` exist so
  later importers attach provenance from day one.

## Roadmap

**Phase 2 — file imports** (CSV/Excel/JSON): the pipeline is
`UPLOAD → PREVIEW → MAP → VALIDATE → DEDUPE → NORMALISE → IMPORT → AUDIT`.
`DataImport` already models batch status and row counts to support incremental,
batched historical migration (500 → 5,000 → 50,000 → 200,000+ invoices).

## Phase 5 — historical documents (implemented)

`PHYSICAL → SCAN → ARCHIVE → OCR → FIELD EXTRACTION → CUSTOMER/PRODUCT MATCH →
MATH VALIDATION → CONFIDENCE → HUMAN REVIEW → DB`.

- **OCR is a provider abstraction** (`services/document_processing/base.py`) — real
  Document-AI providers (Google Document AI, AWS Textract, Azure) plug in via
  `OCR_PROVIDER`; we never build handwriting recognition ourselves. The default
  `structured_json` provider ingests machine-readable invoice JSON so the whole
  pipeline runs and is tested offline.
- **Matching** (`matcher.py`) fuzzy-matches customer/product against master records
  and **never auto-merges below `MATCH_THRESHOLD`** — a weak match yields no id and
  forces review; the original extracted text is always kept on the line (spec §8).
- **Validation** (`validator.py`) checks line/invoice arithmetic; issues are
  flagged, never silently corrected (spec §13).
- **Staging & review queue** — extractions land in `extracted_invoices`
  (`AI_EXTRACTED` if high-confidence & fully matched & arithmetic-clean, else
  `NEEDS_REVIEW`). They are **kept out of analytics** until a manager approves; on
  approval they materialise into a real, `VERIFIED` `Invoice` linked to the source
  document. Reject records the reason and creates nothing.
- **Endpoints**: `POST /documents` (upload+extract), `GET /documents`,
  `GET /extractions` (queue), `GET /extractions/{id}`,
  `POST /extractions/{id}/approve|reject`. Batches reuse the `DataImport` model,
  so historical migration proceeds incrementally (500 → 5,000 → 200,000+).
