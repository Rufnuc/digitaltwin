"""CSV ingestion pipeline tests (spec §15, §42)."""
from __future__ import annotations

import io
import json

from sqlalchemy import func, select

from app.models.customer import Customer
from app.services import ingestion

CUSTOMER_CSV = b"""cust_code,cust_name,city,type
IMP-001,Imported One,Central,WHOLESALE
IMP-002,Imported Two,North,RETAIL
IMP-001,Duplicate Code,East,RETAIL
,No Code,West,RETAIL
"""


def test_preview_lists_columns(db):
    prev = ingestion.preview(CUSTOMER_CSV)
    assert prev["columns"] == ["cust_code", "cust_name", "city", "type"]
    assert len(prev["sample_rows"]) == 4
    assert "customers" in prev["importable_entities"]


def test_import_with_mapping_dedupe_and_required(db):
    mapping = {
        "cust_code": "code",
        "cust_name": "name",
        "city": "location",
        "type": "customer_type",
    }
    result = ingestion.validate_and_import(db, "customers", CUSTOMER_CSV, mapping)
    # 4 data rows: 2 imported, 1 duplicate code, 1 missing required code.
    assert result["rows_total"] == 4
    assert result["rows_imported"] == 2
    assert result["rows_failed"] == 2
    count = db.scalar(select(func.count(Customer.id)))
    assert count == 2
    imported = db.scalar(select(Customer).where(Customer.code == "IMP-001"))
    assert imported.name == "Imported One"
    assert imported.data_origin == "REAL"
    assert imported.extraction_method == "csv_import"


def test_import_endpoint_roundtrip(client, auth_headers):
    mapping = {"cust_code": "code", "cust_name": "name"}
    files = {"file": ("customers.csv", io.BytesIO(CUSTOMER_CSV), "text/csv")}
    data = {"entity_type": "customers", "mapping": json.dumps(mapping)}
    r = client.post("/api/v1/imports", headers=auth_headers("STAFF"), files=files, data=data)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["rows_imported"] == 2
    assert body["import_id"] is not None
    # Batch is listed.
    lst = client.get("/api/v1/imports", headers=auth_headers("STAFF"))
    assert lst.status_code == 200
    assert any(b["id"] == body["import_id"] for b in lst.json()["items"])
