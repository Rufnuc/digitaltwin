"""Central enumerations.

These encode the platform's fundamental design rule (spec §49): the system must
always know the epistemic status of every value it holds. `DataOrigin` and
`VerificationStatus` are attached to imported/derived business data throughout.
"""
from __future__ import annotations

from enum import Enum


class DataOrigin(str, Enum):
    """Where a value came from and how much we should trust it as fact.

    Never conflate these. A FORECAST is not a FACT; DEMO is never REAL.
    """

    REAL = "REAL"                    # verified real business transaction/record
    DEMO = "DEMO"                    # synthetic seed data, never to be shown as real
    ESTIMATED = "ESTIMATED"          # derived/imputed where source was incomplete
    MISSING = "MISSING"              # known-absent; recorded so gaps are explicit
    ASSUMPTION = "ASSUMPTION"        # an input the user/model assumed
    MODEL_OUTPUT = "MODEL_OUTPUT"    # produced by the simulation engine
    FORECAST = "FORECAST"            # a projected future value with uncertainty
    AI_INTERPRETATION = "AI_INTERPRETATION"  # LLM explanation, never a raw number


class VerificationStatus(str, Enum):
    """Human/automated verification state of an extracted or imported record."""

    VERIFIED = "VERIFIED"
    AI_EXTRACTED = "AI_EXTRACTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    PENDING = "PENDING"
    REJECTED = "REJECTED"


class Role(str, Enum):
    """RBAC roles, ordered most→least privileged (see core.security.role_at_least)."""

    ADMIN = "ADMIN"
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    ANALYST = "ANALYST"
    STAFF = "STAFF"
    VIEWER = "VIEWER"


# Privilege ordering used for hierarchical checks.
ROLE_ORDER: list[Role] = [
    Role.VIEWER,
    Role.STAFF,
    Role.ANALYST,
    Role.MANAGER,
    Role.OWNER,
    Role.ADMIN,
]


class CustomerType(str, Enum):
    RETAIL = "RETAIL"
    WHOLESALE = "WHOLESALE"
    TRADE = "TRADE"
    OTHER = "OTHER"


class EntityStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    PROSPECT = "PROSPECT"
    ARCHIVED = "ARCHIVED"


class SimulationStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ScenarioType(str, Enum):
    """Extensible catalogue of scenario kinds the simulation engine understands.

    Phase 1 implements PRICE_CHANGE deterministically; the rest are registered so
    the API surface and storage are stable while engines are added in Phase 3.
    """

    PRICE_CHANGE = "price_change"
    DEMAND_CHANGE = "demand_change"
    SUPPLIER_COST_CHANGE = "supplier_cost_change"
    COST_CHANGE = "cost_change"
    HEADCOUNT_CHANGE = "headcount_change"
    BRANCH_EXPANSION = "branch_expansion"
    CUSTOM = "custom"


class ImportStatus(str, Enum):
    UPLOADED = "UPLOADED"
    PREVIEWED = "PREVIEWED"
    MAPPED = "MAPPED"
    VALIDATED = "VALIDATED"
    IMPORTED = "IMPORTED"
    FAILED = "FAILED"


class DocumentStatus(str, Enum):
    UPLOADED = "UPLOADED"
    ARCHIVED = "ARCHIVED"
    OCR_PENDING = "OCR_PENDING"
    OCR_COMPLETE = "OCR_COMPLETE"
    EXTRACTED = "EXTRACTED"
    FAILED = "FAILED"


class AlertSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AuditAction(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    RUN_SIMULATION = "RUN_SIMULATION"
    IMPORT = "IMPORT"
    VERIFY = "VERIFY"
    AI_QUERY = "AI_QUERY"
