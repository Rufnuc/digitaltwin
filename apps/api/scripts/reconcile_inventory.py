#!/usr/bin/env python
"""One-time inventory reconciliation CLI (legacy-Inventory cutover).

Dry-run by default — prints products whose lot-derived on-hand disagrees with the
legacy Inventory scalar, and changes nothing::

    .venv/bin/python -m scripts.reconcile_inventory

Apply the correction (explicit, audited; aligns the legacy scalar to the lot ledger,
only for products that have lots)::

    .venv/bin/python -m scripts.reconcile_inventory --apply

Run from the apps/api directory so `app` is importable.
"""
from __future__ import annotations

import argparse
import sys

from app.db.session import SessionLocal
from app.services import inventory_reconcile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile legacy Inventory to the lot ledger.")
    parser.add_argument("--apply", action="store_true",
                        help="write the correction (default is a dry-run report)")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        result = inventory_reconcile.reconcile(db, apply=args.apply)
    finally:
        db.close()

    items = result["items"]
    mode = result["mode"].upper()
    print(f"[{mode}] {result['divergent_products']} product(s) diverge "
          f"between the lot ledger and the legacy Inventory scalar.")
    for d in items:
        print(f"  - {d['code'] or d['product_id']} {d['name'] or ''}: "
              f"lots={d['lot_on_hand']} legacy={d['legacy_on_hand']} "
              f"delta={d['delta']:+d}")
    if not args.apply and items:
        print("\nThis was a DRY RUN. Re-run with --apply to align the legacy scalar "
              "to the lot ledger (audited).")
    elif args.apply:
        print("\nApplied: the legacy Inventory scalar now matches the lot ledger.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
