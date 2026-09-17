"""True-concurrency proof for stock-sale and payment row locking (Postgres only).

SQLite serializes writers and ignores ``FOR UPDATE``, so it cannot prove the locks
added in stock.py / receivables.py actually prevent oversell / overpay under two
simultaneous writers. This module runs the real race against Postgres with two
threads, each on its own connection, released together by a barrier.

It is SKIPPED unless a Postgres URL is available (``POSTGRES_TEST_URL`` env, or a
``postgresql`` DATABASE_URL in the repo-root .env). It creates a throwaway database
``digitaltwin_conc_test``, runs the race, and drops it — the live DB is untouched.
"""
from __future__ import annotations

import os
import threading
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

pytest.importorskip("psycopg")


def _postgres_admin_url() -> str | None:
    url = os.environ.get("POSTGRES_TEST_URL")
    if not url:
        env = Path(__file__).resolve().parents[3] / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.strip().startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not url or not url.startswith("postgresql"):
        return None
    return url


_ADMIN_URL = _postgres_admin_url()
_TEST_DB = "digitaltwin_conc_test"

pytestmark = pytest.mark.skipif(
    _ADMIN_URL is None, reason="no Postgres URL available (set POSTGRES_TEST_URL)"
)


@pytest.fixture(scope="module")
def pg_sessionmaker():
    from app.models import Base  # fully-populated metadata

    base = make_url(_ADMIN_URL)
    # Connect to the maintenance DB to (re)create the throwaway test DB.
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS {_TEST_DB} WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE {_TEST_DB}'))
    admin.dispose()

    engine = create_engine(base.set(database=_TEST_DB))
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield Session
    finally:
        engine.dispose()
        admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS {_TEST_DB} WITH (FORCE)'))
        admin.dispose()


def _run_concurrently(fn, n=2):
    """Run `fn(i)` in `n` threads released together; return list of (ok, error)."""
    barrier = threading.Barrier(n)
    results: list[tuple[bool, str | None]] = [(False, None)] * n

    def worker(i):
        barrier.wait()
        try:
            fn(i)
            results[i] = (True, None)
        except Exception as e:  # noqa: BLE001
            results[i] = (False, type(e).__name__ + ": " + str(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def test_concurrent_sales_cannot_oversell(pg_sessionmaker):
    from app.models.product import Product
    from app.models.warehouse import Warehouse
    from app.services import stock

    Session = pg_sessionmaker
    s = Session()
    p = Product(code="CONC-P", name="Conc Pump", purchase_cost=100, selling_price=200)
    wh = Warehouse(code="CONC-WH", name="Conc WH")
    s.add_all([p, wh])
    s.commit()
    pid, wid = p.id, wh.id
    stock.receive_stock(s, product_id=pid, warehouse_id=wid, quantity=5, unit_cost=100)
    s.commit()
    s.close()

    def sell_last_five(_i):
        sess = Session()
        try:
            stock.allocate_for_sale(sess, product_id=pid, warehouse_id=wid, quantity=5,
                                    commit=True)
        finally:
            sess.close()

    results = _run_concurrently(sell_last_five, n=2)
    oks = [r for r in results if r[0]]
    assert len(oks) == 1, f"exactly one sale should win, got {results}"

    check = Session()
    assert stock.on_hand(check, pid, wid) == 0  # never negative
    check.close()


def test_concurrent_payments_cannot_exceed_balance(pg_sessionmaker):
    from sqlalchemy import func, select

    from app.models.invoice import Invoice
    from app.models.payment import Payment
    from app.services import receivables

    Session = pg_sessionmaker
    s = Session()
    inv = Invoice(invoice_number="CONC-INV", invoice_date=date(2026, 1, 1), total=1000)
    s.add(inv)
    s.commit()
    inv_id = inv.id
    s.close()

    def pay_full(_i):
        sess = Session()
        try:
            r = receivables.record_payment(sess, invoice_id=inv_id, amount=1000, method="cash")
            if r.get("status") != "OK":
                raise RuntimeError(r.get("error", "rejected"))
        finally:
            sess.close()

    results = _run_concurrently(pay_full, n=2)
    oks = [r for r in results if r[0]]
    assert len(oks) == 1, f"exactly one payment should win, got {results}"

    check = Session()
    total_paid = check.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.invoice_id == inv_id, Payment.status == "CONFIRMED")
    )
    assert float(total_paid) == 1000.0  # not 2000
    check.close()
