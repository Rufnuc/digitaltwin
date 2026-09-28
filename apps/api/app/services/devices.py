"""Device binding: restrict who may sign in from where by tying an account to
approved browsers/devices. Enforced for the SALESGIRL role and any user with
``device_locked`` set. A new device lands as PENDING until an admin approves it."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Role
from app.models.user import User, UserDevice


class DeviceError(Exception):
    """Login refused because of device binding. ``code`` drives the message shown."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def device_required(user: User) -> bool:
    """True when this account may only sign in from an approved device."""
    return user.role == Role.SALESGIRL.value or bool(getattr(user, "device_locked", False))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def check_login_device(db: Session, user: User, device_id: str | None,
                       label: str | None) -> None:
    """Gate a login by device. No-op for unrestricted accounts. Otherwise:
    - APPROVED device → allowed (stamps last_seen);
    - unknown device → recorded as PENDING, login refused;
    - PENDING/BLOCKED → login refused.
    Raises DeviceError on refusal."""
    if not device_required(user):
        return
    if not device_id:
        raise DeviceError("device_required",
                          "This account can only sign in from an approved device.")

    dev = db.scalar(select(UserDevice).where(
        UserDevice.user_id == user.id, UserDevice.device_id == device_id))
    if dev is None:
        # First time this device is seen for the account: record it for approval.
        db.add(UserDevice(user_id=user.id, device_id=device_id,
                          label=(label or None), status="PENDING",
                          first_seen=_now(), last_seen=_now()))
        db.commit()
        raise DeviceError("pending",
                          "This device isn’t approved yet. Ask the owner to approve it "
                          "in Settings → Users, then sign in again.")
    if dev.status == "BLOCKED":
        dev.last_seen = _now()
        db.commit()
        raise DeviceError("blocked", "This device has been blocked. Contact the owner.")
    if dev.status != "APPROVED":
        dev.last_seen = _now()
        if label and not dev.label:
            dev.label = label
        db.commit()
        raise DeviceError("pending",
                          "This device is still awaiting approval by the owner.")
    # Approved.
    dev.last_seen = _now()
    if label and not dev.label:
        dev.label = label
    db.commit()


def _to_dict(d: UserDevice) -> dict:
    return {
        "id": d.id, "device_id": d.device_id, "label": d.label, "status": d.status,
        "first_seen": d.first_seen.isoformat() if d.first_seen else None,
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        "approved_by_user_id": d.approved_by_user_id,
    }


def list_devices(db: Session, user_id: int) -> list[dict]:
    rows = db.scalars(
        select(UserDevice).where(UserDevice.user_id == user_id)
        .order_by(UserDevice.last_seen.desc().nullslast(), UserDevice.id.desc())
    ).all()
    return [_to_dict(d) for d in rows]


def set_status(db: Session, user_id: int, device_pk: int, status: str,
               approver_id: int | None) -> dict | None:
    if status not in ("APPROVED", "BLOCKED", "PENDING"):
        return {"error": f"invalid status {status}"}
    dev = db.get(UserDevice, device_pk)
    if dev is None or dev.user_id != user_id:
        return None
    dev.status = status
    dev.approved_by_user_id = approver_id if status == "APPROVED" else None
    db.commit()
    db.refresh(dev)
    return _to_dict(dev)


def delete_device(db: Session, user_id: int, device_pk: int) -> bool:
    dev = db.get(UserDevice, device_pk)
    if dev is None or dev.user_id != user_id:
        return False
    db.delete(dev)
    db.commit()
    return True
