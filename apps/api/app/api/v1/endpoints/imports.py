from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import AuditAction, ImportStatus, Role
from app.models.provenance import DataImport
from app.models.user import User
from app.services import audit, ingestion

router = APIRouter(tags=["imports"])


@router.get("/imports/entities")
def importable_entities(_: User = Depends(get_current_user)) -> dict:
    return {
        "entities": {
            name: [
                {"name": f.name, "type": f.type, "required": f.required} for f in spec.fields
            ]
            for name, spec in ingestion.ENTITY_SPECS.items()
        }
    }


@router.post("/imports/preview")
async def preview_import(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
) -> dict:
    content = await file.read()
    try:
        return ingestion.preview(content)
    except Exception as e:  # noqa: BLE001 - surface parse errors to the client
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not parse CSV: {e}") from None


@router.post("/imports", status_code=status.HTTP_201_CREATED)
async def commit_import(
    entity_type: str = Form(...),
    mapping: str = Form(...),  # JSON: {source_column: target_field}
    file: UploadFile = File(...),
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.STAFF)),
) -> dict:
    if entity_type not in ingestion.ENTITY_SPECS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown entity_type '{entity_type}'")
    try:
        mapping_dict = json.loads(mapping)
    except json.JSONDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "mapping must be valid JSON") from None

    content = await file.read()

    # Create the batch record first so rows can link to it (spec §11/§42).
    batch = DataImport(
        filename=file.filename,
        file_format="csv",
        status=ImportStatus.VALIDATED.value,
        created_by_id=user.id,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    try:
        result = ingestion.validate_and_import(
            db, entity_type, content, mapping_dict, data_import_id=batch.id, commit=True
        )
    except ValueError as e:
        batch.status = ImportStatus.FAILED.value
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None

    batch.rows_total = result["rows_total"]
    batch.rows_imported = result["rows_imported"]
    batch.rows_failed = result["rows_failed"]
    batch.status = ImportStatus.IMPORTED.value
    db.commit()

    audit.record(
        db,
        action=AuditAction.IMPORT,
        user_id=user.id,
        entity_type=f"import:{entity_type}",
        entity_id=batch.id,
        summary=f"imported {result['rows_imported']}/{result['rows_total']} rows",
    )
    return {"import_id": batch.id, **result}


@router.get("/imports")
def list_imports(
    db: Session = Depends(db_session),
    _: User = Depends(get_current_user),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    rows = db.scalars(
        select(DataImport).order_by(DataImport.id.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "items": [
            {
                "id": b.id,
                "filename": b.filename,
                "status": b.status,
                "rows_total": b.rows_total,
                "rows_imported": b.rows_imported,
                "rows_failed": b.rows_failed,
                "created_at": b.created_at.isoformat(),
            }
            for b in rows
        ]
    }
