"""Phase-2 remediation: confirm-gated assistant writes, idempotency TTL,
login rate-limit, purge-demo completeness, inventory reconciliation."""
from __future__ import annotations

from app.core.config import settings
from app.services.ai import confirm as confirm_mod


# --- Item 2: confirm-gated assistant writes --------------------------------
class _U:
    def __init__(self, role="OWNER", uid=1):
        self.role = role
        self.id = uid


def test_confirm_executes_the_proposed_write(db, monkeypatch):
    from app.services.ai.tools import execute_tool
    monkeypatch.setattr(settings, "ASSISTANT_ALLOW_WRITES", True)
    prop = execute_tool(db, "create_customer", {"name": "Confirm Co"}, user=_U())
    assert prop["status"] == "PROPOSED"
    data = confirm_mod.verify_token(prop["confirmation_token"])
    out = execute_tool(db, data["name"], data["args"], user=_U(), confirmed=True)
    assert out.get("created") == "customer"


def test_confirm_blocked_by_kill_switch(db, monkeypatch):
    from app.services.ai.tools import execute_tool
    # Propose while writes are on, then the kill switch flips off before confirming.
    monkeypatch.setattr(settings, "ASSISTANT_ALLOW_WRITES", True)
    prop = execute_tool(db, "create_customer", {"name": "KS Co"}, user=_U())
    data = confirm_mod.verify_token(prop["confirmation_token"])
    monkeypatch.setattr(settings, "ASSISTANT_ALLOW_WRITES", False)
    out = execute_tool(db, data["name"], data["args"], user=_U(), confirmed=True)
    assert "error" in out and "read-only" in out["error"].lower()


def test_tampered_confirmation_token_rejected():
    tok = confirm_mod.make_token("create_customer", {"name": "X"}, 1)
    raw, sig = tok.split(".", 1)
    assert confirm_mod.verify_token(raw + "." + ("0" * len(sig))) is None


def test_confirm_endpoint_runs_and_enforces_owner(client, auth_headers, db, monkeypatch):
    monkeypatch.setattr(settings, "ASSISTANT_ALLOW_WRITES", True)
    # Build a proposal for the ADMIN user the auth fixture creates.
    admin = db.query(__import__("app.models.user", fromlist=["User"]).User).filter_by(
        email="admin@test.example.com").first() or None
    # Ensure the admin exists via the token factory route:
    from app.core.security import create_access_token
    from app.models.user import User
    if admin is None:
        admin = User(email="admin@test.example.com", full_name="a",
                     hashed_password="x", role="ADMIN")
        db.add(admin)
        db.commit()
        db.refresh(admin)
    token = confirm_mod.make_token("create_customer", {"name": "Endpoint Co"}, admin.id)
    hdr = {"Authorization": f"Bearer {create_access_token(subject=str(admin.id), role='ADMIN')}"}
    r = client.post("/api/v1/assistant/confirm", headers=hdr,
                    json={"confirmation_token": token})
    assert r.status_code == 200, r.text
    assert r.json()["executed"] == "create_customer"


def test_confirm_endpoint_rejects_other_users_token(client, auth_headers, db, monkeypatch):
    monkeypatch.setattr(settings, "ASSISTANT_ALLOW_WRITES", True)
    # A token minted for user 9999 cannot be confirmed by the acting admin.
    token = confirm_mod.make_token("create_customer", {"name": "Nope"}, 9999)
    r = client.post("/api/v1/assistant/confirm", headers=auth_headers("ADMIN"),
                    json={"confirmation_token": token})
    assert r.status_code == 403, r.text


# --- Item 4: idempotency TTL / stranded-key cleanup ------------------------
def _backdate(db, key, minutes):
    from datetime import datetime, timedelta, timezone

    from app.models.idempotency import IdempotencyKey
    row = db.get(IdempotencyKey, key)
    row.created_at = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    db.commit()


def test_live_reservation_blocks_duplicate_but_stranded_is_reclaimed(db):
    from app.services import idempotency
    # First request reserves and (simulating a crash) never completes.
    r1 = idempotency.reserve(db, "k-strand", scope="sell")
    assert r1.replay is None and not r1.in_progress
    db.commit()
    # A second request while it is still "live" is a duplicate → in progress.
    r2 = idempotency.reserve(db, "k-strand", scope="sell")
    assert r2.in_progress is True
    # After the TTL, the stranded reservation is reclaimed so a retry can proceed.
    _backdate(db, "k-strand", minutes=5)
    r3 = idempotency.reserve(db, "k-strand", scope="sell")
    assert r3.replay is None and r3.in_progress is False


def test_completed_key_never_reclaimed(db):
    from app.services import idempotency
    idempotency.reserve(db, "k-done", scope="sell")
    idempotency.complete(db, "k-done", {"status": "OK", "id": 7})
    _backdate(db, "k-done", minutes=60)  # very old, but completed
    r = idempotency.reserve(db, "k-done", scope="sell")
    assert r.replay == {"status": "OK", "id": 7} and not r.in_progress


def test_cleanup_removes_only_stranded_incomplete(db):
    from app.services import idempotency
    idempotency.reserve(db, "old-incomplete", scope="sell")
    db.commit()
    idempotency.reserve(db, "recent-incomplete", scope="sell")
    db.commit()
    idempotency.reserve(db, "old-complete", scope="sell")
    idempotency.complete(db, "old-complete", {"ok": True})
    _backdate(db, "old-incomplete", minutes=10)
    _backdate(db, "old-complete", minutes=10)
    removed = idempotency.cleanup_stranded(db)
    assert removed == 1  # only the old incomplete one
    from app.models.idempotency import IdempotencyKey
    assert db.get(IdempotencyKey, "old-incomplete") is None
    assert db.get(IdempotencyKey, "old-complete") is not None
    assert db.get(IdempotencyKey, "recent-incomplete") is not None


def test_maintenance_sweep_removes_stranded(db):
    from datetime import datetime, timedelta, timezone

    from app.models.idempotency import IdempotencyKey
    from app.services import idempotency, maintenance
    idempotency.reserve(db, "sweep-me", scope="sell")
    db.commit()
    row = db.get(IdempotencyKey, "sweep-me")
    row.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.commit()
    maintenance._sweep_once()  # opens its own session, commits the delete
    db.expire_all()
    assert db.get(IdempotencyKey, "sweep-me") is None


# --- Item 5: login rate limiting -------------------------------------------
def _make_login_user(db, email="lock@test.example.com", password="secret123"):
    from app.core.security import hash_password
    from app.models.user import User
    u = User(email=email, full_name="L", hashed_password=hash_password(password), role="STAFF")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_login_locks_after_max_attempts(client, db, monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 3)
    _make_login_user(db)
    for _ in range(3):
        r = client.post("/api/v1/auth/login",
                        json={"email": "lock@test.example.com", "password": "wrong"})
        assert r.status_code == 401, r.text
    # Now locked: even the CORRECT password is refused with 429.
    r = client.post("/api/v1/auth/login",
                    json={"email": "lock@test.example.com", "password": "secret123"})
    assert r.status_code == 429, r.text


def test_login_succeeds_after_cooldown(client, db, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.models.user import User
    monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 3)
    _make_login_user(db, email="cool@test.example.com")
    for _ in range(3):
        client.post("/api/v1/auth/login",
                    json={"email": "cool@test.example.com", "password": "wrong"})
    # Fast-forward past the cooldown by backdating the lock.
    u = db.scalar(select(User).where(User.email == "cool@test.example.com"))
    u.lockout_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    r = client.post("/api/v1/auth/login",
                    json={"email": "cool@test.example.com", "password": "secret123"})
    assert r.status_code == 200, r.text
    db.expire_all()
    u2 = db.scalar(select(User).where(User.email == "cool@test.example.com"))
    assert u2.failed_login_count == 0 and u2.lockout_until is None  # reset on success


def test_successful_login_resets_failure_counter(client, db, monkeypatch):
    from sqlalchemy import select

    from app.models.user import User
    monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 5)
    _make_login_user(db, email="reset@test.example.com")
    for _ in range(2):
        client.post("/api/v1/auth/login",
                    json={"email": "reset@test.example.com", "password": "wrong"})
    r = client.post("/api/v1/auth/login",
                    json={"email": "reset@test.example.com", "password": "secret123"})
    assert r.status_code == 200, r.text
    db.expire_all()
    u = db.scalar(select(User).where(User.email == "reset@test.example.com"))
    assert u.failed_login_count == 0


# --- Item 6: purge-demo completeness (no orphans) --------------------------
def test_purge_demo_leaves_no_orphaned_demo_linked_rows(client, auth_headers, db):
    from datetime import date

    from sqlalchemy import func, select

    from app.models.customer import Customer
    from app.models.invoice import Invoice
    from app.models.payment import Payment
    from app.models.product import Product
    from app.models.purchase import Purchase, SupplierPayment
    from app.models.supplier import Supplier
    from app.models.warehouse import StockLot, StockMovement, Warehouse
    from app.services import receivables, stock

    DEMO = "DEMO"
    prod = Product(code="DM-P", name="Demo Pump", purchase_cost=100, selling_price=200,
                   data_origin=DEMO)
    cust = Customer(code="DM-C", name="Demo Cust", data_origin=DEMO)
    sup = Supplier(code="DM-S", name="Demo Sup", data_origin=DEMO)
    wh = Warehouse(code="DM-W", name="Demo WH")
    db.add_all([prod, cust, sup, wh])
    db.commit()
    inv = Invoice(invoice_number="DM-INV", invoice_date=date(2026, 1, 1),
                  customer_id=cust.id, total=1000, data_origin=DEMO)
    db.add(inv)
    db.commit()
    # Rows that only REFERENCE demo data (no demo tag of their own):
    receivables.record_payment(db, invoice_id=inv.id, amount=500, method="cash")  # → demo invoice
    stock.receive_stock(db, product_id=prod.id, warehouse_id=wh.id, quantity=10)   # lot + movement
    pur = Purchase(reference="DM-PUR", purchase_date=date(2026, 1, 2), supplier_id=sup.id,
                   total=300, data_origin=DEMO)
    db.add(pur)
    db.commit()
    db.add(SupplierPayment(purchase_id=pur.id, supplier_id=sup.id, amount=300,
                           method="transfer", paid_at=date(2026, 1, 2), status="CONFIRMED"))
    db.commit()

    # Precondition: the demo-linked rows exist.
    assert db.scalar(select(func.count()).select_from(Payment)) >= 1
    assert db.scalar(select(func.count()).select_from(StockLot)) >= 1
    assert db.scalar(select(func.count()).select_from(StockMovement)) >= 1
    assert db.scalar(select(func.count()).select_from(SupplierPayment)) >= 1

    r = client.post("/api/v1/admin/purge-demo", headers=auth_headers("OWNER"))
    assert r.status_code == 200, r.text

    db.expire_all()
    # No orphans: every demo-linked dependent row is gone, and so are the parents.
    assert db.scalar(select(func.count()).select_from(Payment)) == 0
    assert db.scalar(select(func.count()).select_from(StockLot)) == 0
    assert db.scalar(select(func.count()).select_from(StockMovement)) == 0
    assert db.scalar(select(func.count()).select_from(SupplierPayment)) == 0
    assert db.scalar(select(func.count()).select_from(Invoice)
                     .where(Invoice.data_origin == DEMO)) == 0
    assert db.scalar(select(func.count()).select_from(Product)
                     .where(Product.data_origin == DEMO)) == 0


# --- Item 7: inventory reconciliation --------------------------------------
def _prod_with_lot_and_legacy(db, lot_qty, legacy_qty):
    from app.models.inventory import Inventory
    from app.models.product import Product
    from app.models.warehouse import Warehouse
    from app.services import stock
    p = Product(code="RC-P", name="Recon Pump", purchase_cost=100, selling_price=200)
    wh = Warehouse(code="RC-W", name="Recon WH")
    db.add_all([p, wh])
    db.commit()
    stock.receive_stock(db, product_id=p.id, warehouse_id=wh.id, quantity=lot_qty)
    db.add(Inventory(product_id=p.id, quantity_on_hand=legacy_qty, unit_cost=100))
    db.commit()
    return p.id


def test_reconcile_dry_run_reports_without_writing(db):
    from sqlalchemy import select

    from app.models.inventory import Inventory
    from app.services import inventory_reconcile
    pid = _prod_with_lot_and_legacy(db, lot_qty=10, legacy_qty=3)
    r = inventory_reconcile.reconcile(db)  # dry-run
    assert r["mode"] == "dry_run" and r["divergent_products"] == 1
    item = r["items"][0]
    assert item["product_id"] == pid and item["lot_on_hand"] == 10 and item["legacy_on_hand"] == 3
    # Nothing was written.
    db.expire_all()
    inv = db.scalar(select(Inventory).where(Inventory.product_id == pid))
    assert inv.quantity_on_hand == 3


def test_reconcile_apply_aligns_and_is_idempotent(db):
    from sqlalchemy import select

    from app.models.inventory import Inventory
    from app.services import inventory_reconcile
    pid = _prod_with_lot_and_legacy(db, lot_qty=10, legacy_qty=3)
    inventory_reconcile.reconcile(db, apply=True)
    db.expire_all()
    inv = db.scalar(select(Inventory).where(Inventory.product_id == pid))
    assert inv.quantity_on_hand == 10  # aligned to the lot ledger
    # Running again finds nothing to do.
    assert inventory_reconcile.reconcile(db)["divergent_products"] == 0


def test_reconcile_ignores_legacy_only_products(db):
    from app.models.inventory import Inventory
    from app.models.product import Product
    from app.services import inventory_reconcile
    # A product with a legacy scalar but NO lots must not be reported or touched.
    p = Product(code="LO-P", name="Legacy Only", purchase_cost=1, selling_price=2)
    db.add(p)
    db.commit()
    db.add(Inventory(product_id=p.id, quantity_on_hand=50, unit_cost=1))
    db.commit()
    r = inventory_reconcile.reconcile(db)
    assert r["divergent_products"] == 0
