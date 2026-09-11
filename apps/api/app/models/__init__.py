"""Import every model so `Base.metadata` is fully populated (Alembic autogen,
`create_all` in tests, and relationship resolution all rely on this)."""
from app.db.base import Base  # noqa: F401
from app.models.customer import Customer  # noqa: F401
from app.models.events import (  # noqa: F401
    BusinessEvent,
    EconomicData,
    MarketEvent,
    OwnerKnowledge,
)
from app.models.expense import Expense  # noqa: F401
from app.models.inventory import Inventory  # noqa: F401
from app.models.invoice import Invoice, InvoiceLine  # noqa: F401
from app.models.organization import Branch, Employee  # noqa: F401
from app.models.product import Product, ProductPriceHistory  # noqa: F401
from app.models.provenance import DataImport, DataSource, Document  # noqa: F401
from app.models.purchase import Purchase, PurchaseLine  # noqa: F401
from app.models.simulation import SimulationResult, SimulationRun  # noqa: F401
from app.models.supplier import Supplier  # noqa: F401
from app.models.system import Alert, AuditLog, Notification  # noqa: F401
from app.models.user import User  # noqa: F401

__all__ = [
    "Base",
    "User",
    "Customer",
    "Supplier",
    "Product",
    "ProductPriceHistory",
    "Invoice",
    "InvoiceLine",
    "Purchase",
    "PurchaseLine",
    "Inventory",
    "Expense",
    "Branch",
    "Employee",
    "BusinessEvent",
    "MarketEvent",
    "EconomicData",
    "OwnerKnowledge",
    "DataSource",
    "DataImport",
    "Document",
    "SimulationRun",
    "SimulationResult",
    "AuditLog",
    "Alert",
    "Notification",
]
