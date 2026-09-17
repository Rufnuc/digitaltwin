"""Quant — product substitutes and their live availability."""
from __future__ import annotations

from app.models.inventory import Inventory
from app.models.product import Product
from app.services.ai.tools import execute_tool
from app.services.quant import substitutes as subs


def _prod(db, code, price=1000.0, on_hand=0):
    p = Product(code=code, name=f"Part {code}", selling_price=price, purchase_cost=500.0)
    db.add(p)
    db.commit()
    if on_hand:
        db.add(Inventory(product_id=p.id, quantity_on_hand=on_hand))
        db.commit()
    return p


def test_add_list_and_availability(db):
    china = _prod(db, "PISTON-CN")
    turkey = _prod(db, "PISTON-TR", on_hand=12)
    japan = _prod(db, "PISTON-JP", on_hand=0)

    subs.add_substitute(db, china.id, turkey.id, preference_rank=1, note="Turkey origin")
    subs.add_substitute(db, china.id, japan.id, preference_rank=2, note="Japan origin")

    listed = subs.list_substitutes(db, china.id)
    assert [s["substitute_code"] for s in listed] == ["PISTON-TR", "PISTON-JP"]  # by rank
    assert listed[0]["on_hand"] == 12

    av = subs.substitute_availability(db, china.id)
    assert av["substitute_count"] == 2
    assert av["substitutes_in_stock"] == 1        # only Turkey in stock
    assert av["total_substitute_on_hand"] == 12
    assert av["has_cover"] is True


def test_add_is_idempotent_and_guards(db):
    a = _prod(db, "A")
    b = _prod(db, "B")
    subs.add_substitute(db, a.id, b.id, note="v1")
    subs.add_substitute(db, a.id, b.id, preference_rank=3, note="v2")  # updates, not dup
    listed = subs.list_substitutes(db, a.id)
    assert len(listed) == 1 and listed[0]["preference_rank"] == 3 and listed[0]["note"] == "v2"

    assert subs.add_substitute(db, a.id, a.id)["status"] == "ERROR"      # self
    assert subs.add_substitute(db, a.id, 99999)["status"] == "ERROR"     # missing


def test_remove(db):
    a = _prod(db, "RA")
    b = _prod(db, "RB")
    subs.add_substitute(db, a.id, b.id)
    assert subs.remove_substitute(db, a.id, b.id)["status"] == "OK"
    assert subs.substitute_availability(db, a.id)["substitute_count"] == 0
    assert subs.remove_substitute(db, a.id, b.id)["status"] == "NOT_FOUND"


def _staff(db):
    from app.core.security import hash_password
    from app.models.user import User
    u = User(email="staff@sub.example.com", full_name="Staff",
             hashed_password=hash_password("pw123456"), role="STAFF")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_benfieg_substitute_tools(db, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "ASSISTANT_ALLOW_WRITES", True)  # allow the write tool
    _prod(db, "PISTON-CHINA")
    _prod(db, "PISTON-TURKEY", on_hand=8)
    user = _staff(db)

    added = execute_tool(db, "add_substitute", {
        "product": "PISTON-CHINA", "substitute": "PISTON-TURKEY", "note": "Turkey"},
        user=user, confirmed=True)  # confirm-gated write
    assert added["status"] == "OK"

    got = execute_tool(db, "get_substitutes", {"product": "PISTON-CHINA"})
    assert got["substitute_count"] == 1
    assert got["total_substitute_on_hand"] == 8
    assert got["substitutes"][0]["code"] == "PISTON-TURKEY"
