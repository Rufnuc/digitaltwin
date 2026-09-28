"""Create the first OWNER account on a fresh (empty) production database — no demo
data. Idempotent: does nothing if any user already exists.

Reads from env:
  OWNER_EMAIL     (required)  e.g. owner@fidelagric.com
  OWNER_PASSWORD  (required)  min 8 chars
  OWNER_NAME      (optional)  defaults to "Owner"

Run after migrations, once per business database:
  OWNER_EMAIL=... OWNER_PASSWORD=... python -m scripts.create_owner
"""
from __future__ import annotations

import os
import sys

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User


def main() -> int:
    email = (os.environ.get("OWNER_EMAIL") or "").strip().lower()
    password = os.environ.get("OWNER_PASSWORD") or ""
    name = (os.environ.get("OWNER_NAME") or "Owner").strip()

    if not email or not password:
        print("ERROR: set OWNER_EMAIL and OWNER_PASSWORD env vars.", file=sys.stderr)
        return 2
    if len(password) < 8:
        print("ERROR: OWNER_PASSWORD must be at least 8 characters.", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            existing = db.query(User).filter(User.email == email).first()
            print(f"Users already exist — skipping. ({'this email present' if existing else 'other users present'})")
            return 0
        db.add(User(email=email, full_name=name,
                    hashed_password=hash_password(password), role="OWNER"))
        db.commit()
        print(f"Created OWNER account: {email}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
