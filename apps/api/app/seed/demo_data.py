"""Deterministic DEMO data generator (spec §41).

Every generated record is tagged DataOrigin.DEMO so the platform — and the UI —
can always tell synthetic data from real business data. The dataset is internally
consistent (invoice arithmetic balances, COGS derives from product cost) so
analytics and simulations produce meaningful, non-random results.

Run:  python -m app.seed.demo_data           (seeds; creates SQLite tables if used)
      python -m app.seed.demo_data --reset   (drops & recreates all tables first)
"""
from __future__ import annotations

import argparse
import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.enums import AlertSeverity, CustomerType, DataOrigin, Role, VerificationStatus
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.customer import Customer
from app.models.events import OwnerKnowledge
from app.models.expense import Expense
from app.models.inventory import Inventory
from app.models.invoice import Invoice, InvoiceLine
from app.models.organization import Branch, Employee
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.system import Alert
from app.models.user import User

DEMO = DataOrigin.DEMO.value
VERIFIED = VerificationStatus.VERIFIED.value
SEED = 42

# Naira magnitude factor. Applied uniformly to every monetary random so demo
# figures read as realistic Nigerian Naira amounts while all ratios/margins
# (and therefore analytics/simulation results) stay identical.
SCALE = 600

# Demo login accounts (dev only — documented in README).
DEMO_USERS = [
    ("owner@demo.example.com", "Demo Owner", "owner12345", Role.OWNER),
    ("admin@demo.example.com", "Demo Admin", "admin12345", Role.ADMIN),
    ("salesgirl@demo.example.com", "Demo Salesgirl", "sales12345", Role.SALESGIRL),
]

CATEGORIES = ["Engine", "Brakes", "Electrical", "Suspension", "Filters", "Body"]
PRODUCT_NOUNS = ["Oil pump", "Brake pad", "Alternator", "Shock absorber", "Air filter",
                 "Radiator", "Clutch kit", "Spark plug", "Fuel pump", "Timing belt"]


def _p(mixin_obj):
    mixin_obj.data_origin = DEMO
    mixin_obj.verification_status = VERIFIED
    return mixin_obj


def seed(db: Session) -> dict:
    rnd = random.Random(SEED)

    # --- Users ---
    for email, name, pw, role in DEMO_USERS:
        if not db.query(User).filter_by(email=email).first():
            db.add(User(email=email, full_name=name, hashed_password=hash_password(pw),
                        role=role.value))
    db.commit()

    # --- Branches ---
    branches = [
        Branch(code="BR-MAIN", name="Main Branch", location="Central Market",
               opened_on="2001-03-01"),
        Branch(code="BR-NORTH", name="North Branch", location="North Depot",
               opened_on="2012-06-15"),
    ]
    db.add_all(branches)
    db.commit()

    # --- Employees ---
    for i in range(6):
        db.add(Employee(code=f"EMP-{i+1:03d}", name=f"Employee {i+1}",
                        role_title=rnd.choice(["Sales", "Storekeeper", "Manager", "Driver"]),
                        branch_id=branches[i % len(branches)].id,
                        monthly_cost=round(rnd.uniform(400, 1200) * SCALE, 2),
                        hired_on="2015-01-10"))
    db.commit()

    # --- Suppliers ---
    suppliers = []
    for i in range(5):
        s = Supplier(code=f"SUP-{i+1:03d}", name=f"Supplier {i+1}",
                     location=rnd.choice(["Local", "Import - Asia", "Import - Europe"]),
                     currency="NGN", payment_terms=rnd.choice(["NET30", "NET60", "COD"]),
                     lead_time_days=rnd.randint(3, 45),
                     reliability_score=round(rnd.uniform(0.7, 0.99), 2))
        _p(s)
        suppliers.append(s)
    db.add_all(suppliers)
    db.commit()

    # --- Products (cost < price for positive margin) ---
    products = []
    for i in range(30):
        cost = round(rnd.uniform(5, 200) * SCALE, 2)
        price = round(cost * rnd.uniform(1.25, 1.9), 2)
        noun = PRODUCT_NOUNS[i % len(PRODUCT_NOUNS)]
        pr = Product(code=f"PRD-{i+1:04d}", part_number=f"PN{1000+i}",
                     name=f"{noun} {200+i}", description=f"{noun} variant {200+i}",
                     category=rnd.choice(CATEGORIES),
                     manufacturer=rnd.choice(["OEM", "Aftermarket A", "Aftermarket B"]),
                     supplier_id=rnd.choice(suppliers).id,
                     purchase_cost=cost, selling_price=price,
                     reorder_level=rnd.randint(5, 20), reorder_quantity=rnd.randint(20, 100),
                     lead_time_days=rnd.randint(3, 30))
        _p(pr)
        products.append(pr)
    db.add_all(products)
    db.commit()

    # --- Customers ---
    customers = []
    for i in range(20):
        c = Customer(code=f"CUS-{i+1:04d}", name=f"Customer {i+1}",
                     location=rnd.choice(["Central", "North", "East", "West"]),
                     customer_type=rnd.choice(list(CustomerType)).value,
                     acquisition_date=date(2018, 1, 1) + timedelta(days=rnd.randint(0, 2000)))
        _p(c)
        customers.append(c)
    db.add_all(customers)
    db.commit()

    # --- 24 months of invoices ---
    today = date.today()
    start = date(today.year - 2, today.month, 1)
    invoice_count = 0
    line_count = 0
    inv_no = 1
    for m in range(24):
        month_start = date(start.year + (start.month - 1 + m) // 12,
                           (start.month - 1 + m) % 12 + 1, 1)
        # Seasonal-ish monthly volume.
        n_invoices = rnd.randint(4, 9)
        for _ in range(n_invoices):
            cust = rnd.choice(customers)
            inv_date = month_start + timedelta(days=rnd.randint(0, 26))
            inv = Invoice(invoice_number=f"INV-{inv_date.year}-{inv_no:05d}",
                          invoice_date=inv_date, customer_id=cust.id,
                          branch_id=rnd.choice(branches).id, currency="NGN",
                          discount=0, tax=0)
            _p(inv)
            subtotal = 0.0
            for _ in range(rnd.randint(1, 5)):
                prod = rnd.choice(products)
                qty = rnd.randint(1, 8)
                unit_price = float(prod.selling_price)
                lt = round(qty * unit_price, 2)
                subtotal += lt
                line = InvoiceLine(product_id=prod.id, original_description=prod.name,
                                   quantity=qty, unit_price=unit_price, line_total=lt,
                                   unit_cost=float(prod.purchase_cost))
                _p(line)
                inv.lines.append(line)
                line_count += 1
            tax = round(subtotal * 0.05, 2)
            inv.subtotal = round(subtotal, 2)
            inv.tax = tax
            inv.total = round(subtotal + tax, 2)
            db.add(inv)
            invoice_count += 1
            inv_no += 1
            # keep customer last_purchase_date coherent
            if cust.last_purchase_date is None or inv_date > cust.last_purchase_date:
                cust.last_purchase_date = inv_date
            if cust.first_purchase_date is None or inv_date < cust.first_purchase_date:
                cust.first_purchase_date = inv_date
    db.commit()

    # --- Inventory (one row per product at main branch) ---
    for prod in products:
        inv_row = Inventory(product_id=prod.id, branch_id=branches[0].id,
                            quantity_on_hand=rnd.randint(0, 120),
                            unit_cost=float(prod.purchase_cost),
                            safety_stock=prod.reorder_level)
        _p(inv_row)
        db.add(inv_row)
    db.commit()

    # --- Expenses over 24 months ---
    exp_categories = ["Rent", "Utilities", "Salaries", "Transport", "Marketing", "Misc"]
    for m in range(24):
        month_start = date(start.year + (start.month - 1 + m) // 12,
                           (start.month - 1 + m) % 12 + 1, 1)
        for cat in exp_categories:
            # Right-sized so total opex sits below gross profit (a solvent demo
            # business). Salaries are the largest line; the rest are smaller.
            base = (2200 if cat == "Salaries" else rnd.uniform(150, 900)) * SCALE
            e = Expense(expense_date=month_start, category=cat,
                        description=f"{cat} for {month_start:%Y-%m}",
                        amount=round(base * rnd.uniform(0.85, 1.15), 2), currency="NGN",
                        branch_id=branches[0].id)
            _p(e)
            db.add(e)
    db.commit()

    # --- A demo alert + owner knowledge, clearly labelled ---
    db.add(Alert(severity=AlertSeverity.LOW.value, category="demo",
                 title="Demo dataset loaded",
                 body="This workspace currently contains DEMO data only.",
                 data_origin=DEMO))
    db.add(OwnerKnowledge(
        topic="history",
        content="(DEMO) Business established ~1994; expanded to North branch in 2012.",
        related_entity_type="branch"))
    db.commit()

    return {"invoices": invoice_count, "invoice_lines": line_count,
            "products": len(products), "customers": len(customers),
            "suppliers": len(suppliers)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="drop & recreate all tables")
    args = parser.parse_args()

    if args.reset:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        counts = seed(db)
        print(f"Seeded DEMO data: {counts}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
