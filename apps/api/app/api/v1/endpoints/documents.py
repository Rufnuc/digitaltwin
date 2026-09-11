from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import AuditAction, DocumentStatus, Role, VerificationStatus
from app.models.extraction import ExtractedInvoice
from app.models.provenance import Document
from app.models.user import User
from app.services import audit
from app.services.document_processing import pipeline
from app.services.storage import get_storage

router = APIRouter(tags=["documents"])


def _doc_dict(d: Document) -> dict:
    return {
        "id": d.id,
        "filename": d.filename,
        "content_type": d.content_type,
        "status": d.status,
        "ocr_confidence": d.ocr_confidence,
        "created_at": d.created_at.isoformat(),
    }


def _staged_dict(s: ExtractedInvoice) -> dict:
    return {
        "id": s.id,
        "document_id": s.document_id,
        "status": s.status,
        "overall_confidence": s.overall_confidence,
        "extracted": s.extracted,
        "matched": s.matched,
        "validation": s.validation,
        "created_invoice_id": s.created_invoice_id,
        "review_notes": s.review_notes,
        "created_at": s.created_at.isoformat(),
    }


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.STAFF)),
) -> dict:
    """Archive a source document and run the extraction pipeline (spec §12)."""
    data = await file.read()
    key = get_storage().save(data, file.filename or "document", file.content_type)
    doc = Document(
        filename=file.filename or "document",
        content_type=file.content_type,
        storage_key=key,
        status=DocumentStatus.UPLOADED.value,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        staged = pipeline.process_document(db, doc, data)
    except (ValueError, NotImplementedError) as e:
        doc.status = DocumentStatus.FAILED.value
        db.commit()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Extraction failed: {e}"
        ) from None

    audit.record(
        db, action=AuditAction.IMPORT, user_id=user.id, entity_type="document",
        entity_id=doc.id,
        summary=f"extracted -> {staged.status} (conf {staged.overall_confidence})",
    )
    return {"document": _doc_dict(doc), "extraction": _staged_dict(staged)}


@router.get("/documents")
def list_documents(
    db: Session = Depends(db_session),
    _: User = Depends(get_current_user),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    rows = db.scalars(
        select(Document).order_by(Document.id.desc()).limit(limit).offset(offset)
    ).all()
    return {"items": [_doc_dict(d) for d in rows]}


@router.get("/extractions")
def review_queue(
    db: Session = Depends(db_session),
    _: User = Depends(get_current_user),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    stmt = select(ExtractedInvoice).order_by(ExtractedInvoice.id.desc())
    if status_filter:
        stmt = stmt.where(ExtractedInvoice.status == status_filter)
    else:
        # Default: things that still need a human.
        stmt = stmt.where(
            ExtractedInvoice.status.in_(
                [VerificationStatus.NEEDS_REVIEW.value, VerificationStatus.AI_EXTRACTED.value]
            )
        )
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return {"items": [_staged_dict(s) for s in rows]}


@router.get("/extractions/{extraction_id}")
def get_extraction(
    extraction_id: int, db: Session = Depends(db_session), _: User = Depends(get_current_user)
) -> dict:
    s = db.get(ExtractedInvoice, extraction_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Extraction not found")
    return _staged_dict(s)


class ApproveRequest(BaseModel):
    customer_id: int | None = None
    line_product_ids: list[int | None] | None = None


class RejectRequest(BaseModel):
    notes: str | None = None


@router.post("/extractions/{extraction_id}/approve")
def approve(
    extraction_id: int,
    payload: ApproveRequest,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.MANAGER)),
) -> dict:
    s = db.get(ExtractedInvoice, extraction_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Extraction not found")
    if s.status in (VerificationStatus.VERIFIED.value, VerificationStatus.REJECTED.value):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Extraction already {s.status}")

    corrections = payload.model_dump(exclude_none=True)
    invoice = pipeline.approve_extraction(db, s, user.id, corrections or None)
    audit.record(
        db, action=AuditAction.VERIFY, user_id=user.id, entity_type="extracted_invoice",
        entity_id=s.id, summary=f"approved -> invoice {invoice.id}",
    )
    return {"invoice_id": invoice.id, "extraction": _staged_dict(s)}


@router.post("/extractions/{extraction_id}/reject")
def reject(
    extraction_id: int,
    payload: RejectRequest,
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.MANAGER)),
) -> dict:
    s = db.get(ExtractedInvoice, extraction_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Extraction not found")
    pipeline.reject_extraction(db, s, user.id, payload.notes)
    audit.record(
        db, action=AuditAction.VERIFY, user_id=user.id, entity_type="extracted_invoice",
        entity_id=s.id, summary="rejected",
    )
    return _staged_dict(s)
