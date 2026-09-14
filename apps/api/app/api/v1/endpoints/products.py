"""Product-specific endpoints beyond generic CRUD: a gallery of reference images
per product. Each image is either an uploaded file (stored locally, served by an
unguessable key) or an external URL. One image is the primary (mirrored onto
Product.image_url for list/card views).
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import Role
from app.models.product import Product, ProductImage
from app.models.user import User
from app.services.storage import get_storage

router = APIRouter(tags=["products"])

_MAX_BYTES = 5 * 1024 * 1024
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}


def _require_product(db: Session, product_id: int) -> Product:
    prod = db.get(Product, product_id)
    if prod is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Product {product_id} not found")
    return prod


def _reindex_primary(db: Session, prod: Product) -> None:
    """Keep exactly one primary, and mirror it onto Product.image_url."""
    imgs = list(db.scalars(
        select(ProductImage).where(ProductImage.product_id == prod.id)
        .order_by(ProductImage.sort_order, ProductImage.id)
    ).all())
    primary = next((i for i in imgs if i.is_primary), imgs[0] if imgs else None)
    for i in imgs:
        i.is_primary = i is primary
    prod.image_url = primary.url if primary else None


def _dump(i: ProductImage) -> dict:
    return {"id": i.id, "url": i.url, "is_primary": i.is_primary, "sort_order": i.sort_order}


@router.get("/products/{product_id}/images")
def list_images(
    product_id: int, db: Session = Depends(db_session), _: User = Depends(get_current_user)
) -> dict:
    _require_product(db, product_id)
    rows = db.scalars(
        select(ProductImage).where(ProductImage.product_id == product_id)
        .order_by(ProductImage.sort_order, ProductImage.id)
    ).all()
    return {"items": [_dump(i) for i in rows]}


def _add_image(db: Session, prod: Product, url: str) -> ProductImage:
    orders = db.scalars(
        select(ProductImage.sort_order).where(ProductImage.product_id == prod.id)
    ).all()
    img = ProductImage(
        product_id=prod.id, url=url,
        is_primary=(len(orders) == 0),
        sort_order=(max(orders) + 1) if orders else 0,
    )
    db.add(img)
    db.flush()
    _reindex_primary(db, prod)
    return img


@router.post("/products/{product_id}/image")
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF)),
) -> dict:
    prod = _require_product(db, product_id)
    if file.content_type not in _IMAGE_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "image files only")
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "image too large (max 5MB)")
    key = get_storage().save(data, file.filename or "image", file.content_type)
    img = _add_image(db, prod, f"/api/v1/products/image/{key}")
    db.commit()
    return _dump(img)


class ImageUrlIn(BaseModel):
    url: str


@router.post("/products/{product_id}/image-url")
def add_image_url(
    product_id: int,
    payload: ImageUrlIn,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF)),
) -> dict:
    prod = _require_product(db, product_id)
    url = payload.url.strip()
    if not url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "url is required")
    img = _add_image(db, prod, url)
    db.commit()
    return _dump(img)


@router.post("/products/{product_id}/images/{image_id}/primary")
def set_primary(
    product_id: int, image_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF)),
) -> dict:
    prod = _require_product(db, product_id)
    img = db.get(ProductImage, image_id)
    if img is None or img.product_id != product_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "image not found")
    for i in prod.images:
        i.is_primary = i.id == image_id
    prod.image_url = img.url
    db.commit()
    return {"ok": True, "image_url": prod.image_url}


@router.delete("/products/{product_id}/images/{image_id}")
def delete_image(
    product_id: int, image_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.STAFF)),
) -> dict:
    prod = _require_product(db, product_id)
    img = db.get(ProductImage, image_id)
    if img is None or img.product_id != product_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "image not found")
    # Remove the stored file if it was an upload we own.
    if img.url.startswith("/api/v1/products/image/"):
        key = img.url.rsplit("/", 1)[-1]
        path = get_storage().path_for(key)
        if os.path.isfile(path):
            os.remove(path)
    db.delete(img)
    db.flush()
    _reindex_primary(db, prod)
    db.commit()
    return {"ok": True}


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
