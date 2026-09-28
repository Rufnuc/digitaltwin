"""Import every model so `Base.metadata` is fully populated (Alembic autogen,
`create_all` in tests, and relationship resolution all rely on this)."""
from app.db.base import Base  # noqa: F401
from app.models.assistant import (  # noqa: F401
    AssistantConversation,
    AssistantMessage,
)
from app.models.company import CompanyProfile  # noqa: F401
from app.models.customer import Customer  # noqa: F401
from app.models.events import (  # noqa: F401
    BusinessEvent,
    EconomicData,
    MarketEvent,
    OwnerKnowledge,
)
from app.models.expense import Expense  # noqa: F401
from app.models.extraction import ExtractedInvoice  # noqa: F401
from app.models.idempotency import IdempotencyKey  # noqa: F401
from app.models.inventory import Inventory  # noqa: F401
from app.models.invoice import Invoice, InvoiceLine, InvoiceVersion  # noqa: F401
from app.models.organization import Branch, Employee  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.product import (  # noqa: F401
    Product,
    ProductImage,
    ProductPriceHistory,
    ProductSubstitute,
)
from app.models.provenance import DataImport, DataSource, Document  # noqa: F401
from app.models.purchase import (  # noqa: F401
    Purchase,
    PurchaseDocument,
    PurchaseLine,
    SupplierPayment,
)
from app.models.shipping import VesselTrack  # noqa: F401
from app.models.simulation import SimulationResult, SimulationRun  # noqa: F401
from app.models.supplier import Supplier  # noqa: F401
from app.models.system import Alert, AuditLog, Notification  # noqa: F401
from app.models.user import User, UserDevice  # noqa: F401
from app.models.warehouse import StockLot, StockMovement, Warehouse  # noqa: F401
from app.models.waybill import Waybill  # noqa: F401

__all__ = [
    "Base",
    "User",
    "UserDevice",
    "CompanyProfile",
    "Customer",
    "Supplier",
    "Product",
    "ProductImage",
    "ProductPriceHistory",
    "ProductSubstitute",
    "Invoice",
    "InvoiceLine",
    "InvoiceVersion",
    "Payment",
    "Purchase",
    "SupplierPayment",
    "PurchaseLine",
    "PurchaseDocument",
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
    "ExtractedInvoice",
    "SimulationRun",
    "SimulationResult",
    "VesselTrack",
    "Warehouse",
    "StockLot",
    "StockMovement",
    "AuditLog",
    "Alert",
    "Notification",
    "AssistantConversation",
    "AssistantMessage",
]
