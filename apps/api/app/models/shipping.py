from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VesselTrack(Base):
    """Durable per-vessel state for the AIS shipping monitor.

    The live monitor keeps positions in memory for speed; this table persists the
    slow-moving facts (origin lane, whether the ship declared / reached Nigeria,
    last known position) so a vessel first seen weeks ago is still remembered
    across API restarts. Keyed by MMSI (the ship's AIS identity). All values are
    REAL AIS observations.
    """

    __tablename__ = "vessel_tracks"

    mmsi: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(120), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    sog: Mapped[float | None] = mapped_column(Float, nullable=True)
    cog: Mapped[float | None] = mapped_column(Float, nullable=True)
    ship_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    destination: Mapped[str | None] = mapped_column(String(120), nullable=True)
    eta: Mapped[str | None] = mapped_column(String(40), nullable=True)
    region: Mapped[str] = mapped_column(String(48), default="Unknown")
    origin_region: Mapped[str | None] = mapped_column(String(48), nullable=True)
    bound_for_nigeria: Mapped[bool] = mapped_column(Boolean, default=False)
    arrived_nigeria: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_seen: Mapped[str | None] = mapped_column(String(40), nullable=True)
