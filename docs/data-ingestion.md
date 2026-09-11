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

**Phase 5 — historical paper invoices**: `PHYSICAL → SCAN → ARCHIVE → OCR →
FIELD EXTRACTION → BUSINESS PARSE → CUSTOMER/PRODUCT MATCH → MATH VALIDATION →
CONFIDENCE → HUMAN REVIEW → DB`. OCR is a **provider abstraction**
(`services/document_processing/base.py`); we never build handwriting recognition
ourselves. Product normalisation must never auto-merge below a confidence
threshold — the original description is always retained on the line.
