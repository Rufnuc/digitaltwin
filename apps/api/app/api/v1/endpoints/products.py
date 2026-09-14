"""Product-specific endpoints beyond generic CRUD: a reference image that can be
either uploaded (stored locally) or set from an external URL.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_role
from app.core.enums import Role
from app.models.product import Product
from app.models.user import User
from app.services.storage import get_storage

router = APIRouter(tags=["products"])

_MAX_BYTES = 5 * 1024 * 1024
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}


@router.post("/products/{product_id}/image")
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF)),
) -> dict:
    prod = db.get(Product, product_id)
    if prod is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Product {product_id} not found")
    if file.content_type not in _IMAGE_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "image files only")
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "image too large (max 5MB)")
    key = get_storage().save(data, file.filename or "image", file.content_type)
    prod.image_url = f"/api/v1/products/image/{key}"
    db.commit()
    return {"image_url": prod.image_url}


@router.get("/products/image/{key}")
def get_product_image(key: str) -> FileResponse:
    """Serve a stored product image. The key is an unguessable storage id, so this
    is open (no auth) — an <img> tag can load it directly."""
    if "/" in key or ".." in key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad key")
    path = get_storage().path_for(key)
    if not os.path.isfile(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "image not found")
    return FileResponse(path)
