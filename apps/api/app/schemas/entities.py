"""Read/write schemas for the core business entities.

Kept in one module to keep the CRUD surface consistent. Out models carry
provenance + timestamps; Create/Update models accept only user-settable fields.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.schemas.common import ORMModel, ProvenanceOut, TimestampsOut


# --------------------------------------------------------------------------- #
# Customer
# --------------------------------------------------------------------------- #
class CustomerBase(BaseModel):
    code: str
    name: str
    location: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    customer_type: str = "RETAIL"
    status: str = "ACTIVE"


class CustomerCreate(CustomerBase):
    # Code is auto-generated (CUS-####) when omitted.
    code: str | None = None


class CustomerUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    customer_type: str | None = None
    status: str | None = None


class CustomerOut(CustomerBase, ProvenanceOut, TimestampsOut):
    id: int
    first_purchase_date: date | None = None
    last_purchase_date: date | None = None
    lifetime_revenue: float | None = None
    order_count: int | None = None


# --------------------------------------------------------------------------- #
# Supplier
# --------------------------------------------------------------------------- #
class SupplierBase(BaseModel):
    code: str
    name: str
    location: str | None = None
    currency: str = "NGN"
    payment_terms: str | None = None
    lead_time_days: int | None = None
    status: str = "ACTIVE"


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    currency: str | None = None
    payment_terms: str | None = None
    lead_time_days: int | None = None
    reliability_score: float | None = None
    status: str | None = None


class SupplierOut(SupplierBase, ProvenanceOut, TimestampsOut):
    id: int
    reliability_score: float | None = None


# --------------------------------------------------------------------------- #
# Product
# --------------------------------------------------------------------------- #
class ProductBase(BaseModel):
    code: str
    name: str
    part_number: str | None = None
    description: str | None = None
    category: str | None = None
    manufacturer: str | None = None
    supplier_id: int | None = None
    purchase_cost: float | None = None
    selling_price: float | None = None
    reorder_level: int | None = None
    reorder_quantity: int | None = None
    lead_time_days: int | None = None
    is_active: bool = True


class ProductCreate(ProductBase):
    # Code is auto-generated (PRD-####) when omitted.
    code: str | None = None


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    manufacturer: str | None = None
    supplier_id: int | None = None
    purchase_cost: float | None = None
    selling_price: float | None = None
    reorder_level: int | None = None
    reorder_quantity: int | None = None
    lead_time_days: int | None = None
    is_active: bool | None = None


class ProductOut(ProductBase, ProvenanceOut, TimestampsOut):
    id: int


# --------------------------------------------------------------------------- #
# Branch / Employee
# --------------------------------------------------------------------------- #
class WarehouseBase(BaseModel):
    code: str
    name: str
    location: str | None = None
    address: str | None = None
    type: str = "warehouse"
    status: str = "ACTIVE"


class WarehouseCreate(WarehouseBase):
    pass


class WarehouseUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    address: str | None = None
    type: str | None = None
    status: str | None = None


class WarehouseOut(WarehouseBase, TimestampsOut):
    id: int


class BranchBase(BaseModel):
    code: str
    name: str
    location: str | None = None
    status: str = "ACTIVE"
    opened_on: str | None = None


class BranchCreate(BranchBase):
    pass


class BranchUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    status: str | None = None
    opened_on: str | None = None


class BranchOut(BranchBase, TimestampsOut):
    id: int


class EmployeeBase(BaseModel):
    code: str
    name: str
    role_title: str | None = None
    branch_id: int | None = None
    monthly_cost: float | None = None
    status: str = "ACTIVE"
    hired_on: str | None = None


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    name: str | None = None
    role_title: str | None = None
    branch_id: int | None = None
    monthly_cost: float | None = None
    status: str | None = None
    hired_on: str | None = None


class EmployeeOut(EmployeeBase, TimestampsOut):
    id: int


class ExpenseUpdate(BaseModel):
    expense_date: date | None = None
    category: str | None = None
    description: str | None = None
    amount: float | None = None
    currency: str | None = None
    branch_id: int | None = None


# --------------------------------------------------------------------------- #
# Expense
# --------------------------------------------------------------------------- #
class ExpenseBase(BaseModel):
    expense_date: date
    category: str
    description: str | None = None
    amount: float
    currency: str = "NGN"
    branch_id: int | None = None


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseOut(ExpenseBase, ProvenanceOut, TimestampsOut):
    id: int


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #
class InventoryBase(BaseModel):
    product_id: int
    branch_id: int | None = None
    quantity_on_hand: int = 0
    unit_cost: float | None = None
    safety_stock: int | None = None


class InventoryCreate(InventoryBase):
    pass


class InventoryUpdate(BaseModel):
    quantity_on_hand: int | None = None
    unit_cost: float | None = None
    safety_stock: int | None = None


class InventoryOut(InventoryBase, ProvenanceOut, TimestampsOut):
    id: int


# --------------------------------------------------------------------------- #
# Invoice (+ lines)
# --------------------------------------------------------------------------- #
class InvoiceLineIn(BaseModel):
    product_id: int | None = None
    original_description: str | None = None
    quantity: float = 0
    unit_price: float = 0
    line_total: float = 0
    unit_cost: float | None = None


class InvoiceLineOut(ProvenanceOut, ORMModel):
    id: int
    product_id: int | None = None
    original_description: str | None = None
    quantity: float
    unit_price: float
    line_total: float
    unit_cost: float | None = None


class InvoiceCreate(BaseModel):
    invoice_number: str
    invoice_date: date
    customer_id: int | None = None
    branch_id: int | None = None
    currency: str = "NGN"
    discount: float = 0
    tax: float = 0
    lines: list[InvoiceLineIn] = []


class InvoiceOut(ProvenanceOut, TimestampsOut):
    id: int
    invoice_number: str
    invoice_date: date
    customer_id: int | None = None
    branch_id: int | None = None
    currency: str
    subtotal: float
    discount: float
    tax: float
    total: float
    lines: list[InvoiceLineOut] = []
