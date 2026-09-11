"""Customer & product matching for extracted documents (spec §8, §12).

Handwriting/OCR yields varying descriptions for the same entity ("Oil pump 265",
"Oilpump", ...). We fuzzy-match against master records but NEVER auto-merge below a
confidence threshold — a weak match returns no id and forces human review, and the
original extracted text is always preserved on the line.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.product import Product

# Below this we do not assign a match (leave id None -> needs review).
MATCH_THRESHOLD = 0.6


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def _score(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


@dataclass
class Match:
    id: int | None
    confidence: float
    matched_text: str | None = None


def match_customer(db: Session, name: str | None) -> Match:
    if not name:
        return Match(None, 0.0)
    best: Match = Match(None, 0.0)
    for cid, cname, code in db.execute(
        select(Customer.id, Customer.name, Customer.code)
    ).all():
        for candidate in (cname, code):
            s = _score(name, candidate or "")
            if s > best.confidence:
                best = Match(cid, round(s, 3), candidate)
    return best if best.confidence >= MATCH_THRESHOLD else Match(None, round(best.confidence, 3))


def match_product(db: Session, description: str | None) -> Match:
    if not description:
        return Match(None, 0.0)
    best: Match = Match(None, 0.0)
    for pid, pname, code, part in db.execute(
        select(Product.id, Product.name, Product.code, Product.part_number)
    ).all():
        for candidate in (pname, code, part):
            s = _score(description, candidate or "")
            if s > best.confidence:
                best = Match(pid, round(s, 3), candidate)
    return best if best.confidence >= MATCH_THRESHOLD else Match(None, round(best.confidence, 3))
