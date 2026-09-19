"""CSV data-ingestion pipeline (spec §15, §42).

UPLOAD → PREVIEW → MAP → VALIDATE → DEDUPE → IMPORT → AUDIT.

Extensible via ENTITY_SPECS: a new importable entity is one registry entry. All
imported rows are tagged provenance-wise (DataOrigin.REAL via the API layer,
linked to a DataImport batch) so historical migration can proceed incrementally
in batches while the system stays usable (spec §42).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.expense import Expense
from app.models.product import Product
from app.models.supplier import Supplier


@dataclass
class FieldSpec:
    name: str
    type: str = "str"  # str | float | int | date
    required: bool = False


@dataclass
class EntitySpec:
    model: type
    unique_field: str | None
    fields: list[FieldSpec] = field(default_factory=list)

    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]


ENTITY_SPECS: dict[str, EntitySpec] = {
    "customers": EntitySpec(
        model=Customer,
        unique_field="code",
        fields=[
            FieldSpec("code", "str", True),
            FieldSpec("name", "str", True),
            FieldSpec("location"),
            FieldSpec("contact_email"),
            FieldSpec("contact_phone"),
            FieldSpec("customer_type"),
            FieldSpec("status"),
        ],
    ),
    "products": EntitySpec(
        model=Product,
        unique_field="code",
        fields=[
            FieldSpec("code", "str", True),
            FieldSpec("name", "str", True),
            FieldSpec("part_number"),
            FieldSpec("category"),
            FieldSpec("manufacturer"),
            FieldSpec("purchase_cost", "float"),
            FieldSpec("selling_price", "float"),
        ],
    ),
    "suppliers": EntitySpec(
        model=Supplier,
        unique_field="code",
        fields=[
            FieldSpec("code", "str", True),
            FieldSpec("name", "str", True),
            FieldSpec("location"),
            FieldSpec("currency"),
            FieldSpec("payment_terms"),
            FieldSpec("lead_time_days", "int"),
            FieldSpec("status"),
            # reliability_score is graded by the system, not set at import.
        ],
    ),
    "expenses": EntitySpec(
        model=Expense,
        unique_field=None,
        fields=[
            FieldSpec("expense_date", "date", True),
            FieldSpec("category", "str", True),
            FieldSpec("description"),
            FieldSpec("amount", "float", True),
            FieldSpec("currency"),
        ],
    ),
}


def _decode(content: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def preview(content: bytes, sample: int = 20) -> dict:
    reader = csv.DictReader(io.StringIO(_decode(content)))
    columns = reader.fieldnames or []
    rows = []
    for i, row in enumerate(reader):
        if i >= sample:
            break
        rows.append(row)
    return {"columns": columns, "sample_rows": rows, "importable_entities": list(ENTITY_SPECS)}


def _coerce(value: str, type_: str):
    v = (value or "").strip()
    if v == "":
        return None
    if type_ == "float":
        return float(v.replace(",", ""))
    if type_ == "int":
        return int(float(v))
    if type_ == "date":
        return datetime.strptime(v[:10], "%Y-%m-%d").date()
    return v


def validate_and_import(
    db: Session,
    entity_type: str,
    content: bytes,
    mapping: dict[str, str],
    data_import_id: int | None = None,
    commit: bool = True,
) -> dict:
    """mapping: {source_column: target_field}. Returns a summary with per-row errors."""
    spec = ENTITY_SPECS.get(entity_type)
    if spec is None:
        raise ValueError(f"Unknown entity_type '{entity_type}'")

    valid_fields = set(spec.field_names())
    target_map = {src: tgt for src, tgt in mapping.items() if tgt in valid_fields}

    reader = csv.DictReader(io.StringIO(_decode(content)))
    errors: list[dict] = []
    imported = 0
    total = 0

    # Preload existing unique keys for dedupe.
    existing: set = set()
    if spec.unique_field:
        col = getattr(spec.model, spec.unique_field)
        existing = {r for (r,) in db.execute(select(col)).all()}

    seen_in_file: set = set()

    for line_no, raw in enumerate(reader, start=2):  # row 1 is the header
        total += 1
        record: dict = {}
        try:
            for src, tgt in target_map.items():
                fs = next(f for f in spec.fields if f.name == tgt)
                record[tgt] = _coerce(raw.get(src, ""), fs.type)
            # Required-field validation.
            missing = [
                f.name for f in spec.fields if f.required and record.get(f.name) in (None, "")
            ]
            if missing:
                raise ValueError(f"missing required field(s): {', '.join(missing)}")
            # Dedupe.
            if spec.unique_field:
                key = record.get(spec.unique_field)
                if key in existing or key in seen_in_file:
                    errors.append({"row": line_no, "error": f"duplicate {spec.unique_field}={key}"})
                    continue
                seen_in_file.add(key)
        except (ValueError, StopIteration) as e:
            errors.append({"row": line_no, "error": str(e)})
            continue

        obj = spec.model(**record)
        # Provenance: real imported data, linked to the batch.
        if hasattr(obj, "data_origin"):
            obj.data_origin = "REAL"
            obj.extraction_method = "csv_import"
        if hasattr(obj, "data_import_id") and data_import_id is not None:
            obj.data_import_id = data_import_id
        db.add(obj)
        imported += 1

    if commit:
        db.commit()
    else:
        db.flush()

    return {
        "entity_type": entity_type,
        "rows_total": total,
        "rows_imported": imported,
        "rows_failed": len(errors),
        "errors": errors[:50],
    }
