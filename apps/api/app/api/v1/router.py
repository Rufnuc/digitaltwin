"""Assembles the versioned API surface (spec §38)."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.crud import build_crud_router
from app.api.v1.endpoints import (
    admin,
    agents,
    analytics,
    assistant,
    auth,
    company,
    dashboard,
    documents,
    impact,
    imports,
    invoices,
    market,
    meta,
    notifications,
    quant,
    shipping,
    simulations,
    stock,
)
from app.api.v1.endpoints import (
    audit as audit_ep,
)
from app.api.v1.endpoints import (
    products as products_ep,
)
from app.core.enums import Role
from app.models.customer import Customer
from app.models.expense import Expense
from app.models.inventory import Inventory
from app.models.organization import Branch, Employee
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse
from app.schemas import entities as e

api_router = APIRouter()

# Bespoke resources
api_router.include_router(auth.router)
api_router.include_router(audit_ep.router)
api_router.include_router(dashboard.router)
api_router.include_router(invoices.router, prefix="/invoices")
api_router.include_router(simulations.router)
api_router.include_router(analytics.router)
api_router.include_router(imports.router)
api_router.include_router(assistant.router)
api_router.include_router(documents.router)
api_router.include_router(market.router)
api_router.include_router(impact.router)
api_router.include_router(agents.router)
api_router.include_router(admin.router)
api_router.include_router(shipping.router)
api_router.include_router(notifications.router)
api_router.include_router(stock.router)
api_router.include_router(company.router)
api_router.include_router(products_ep.router)
api_router.include_router(quant.router)
api_router.include_router(meta.router)

# Generic CRUD resources
api_router.include_router(
    build_crud_router(
        model=Customer,
        create_schema=e.CustomerCreate,
        update_schema=e.CustomerUpdate,
        out_schema=e.CustomerOut,
        entity_type="customer",
        tags=["customers"],
        search_fields=("name", "code", "location"),
        auto_code_prefix="CUS-",
    ),
    prefix="/customers",
)
api_router.include_router(
    build_crud_router(
        model=Supplier,
        create_schema=e.SupplierCreate,
        update_schema=e.SupplierUpdate,
        out_schema=e.SupplierOut,
        entity_type="supplier",
        tags=["suppliers"],
        search_fields=("name", "code"),
    ),
    prefix="/suppliers",
)
api_router.include_router(
    build_crud_router(
        model=Product,
        create_schema=e.ProductCreate,
        update_schema=e.ProductUpdate,
        out_schema=e.ProductOut,
        entity_type="product",
        tags=["products"],
        search_fields=("name", "code", "part_number", "category"),
        auto_code_prefix="PRD-",
    ),
    prefix="/products",
)
api_router.include_router(
    build_crud_router(
        model=Expense,
        create_schema=e.ExpenseCreate,
        update_schema=e.ExpenseUpdate,
        out_schema=e.ExpenseOut,
        entity_type="expense",
        tags=["expenses"],
        search_fields=("category", "description"),
    ),
    prefix="/expenses",
)
api_router.include_router(
    build_crud_router(
        model=Branch,
        create_schema=e.BranchCreate,
        update_schema=e.BranchUpdate,
        out_schema=e.BranchOut,
        entity_type="branch",
        tags=["branches"],
        write_role=Role.MANAGER,
        search_fields=("name", "code"),
    ),
    prefix="/branches",
)
api_router.include_router(
    build_crud_router(
        model=Warehouse,
        create_schema=e.WarehouseCreate,
        update_schema=e.WarehouseUpdate,
        out_schema=e.WarehouseOut,
        entity_type="warehouse",
        tags=["warehouses"],
        write_role=Role.MANAGER,
        delete_role=Role.MANAGER,
        search_fields=("name", "code", "location"),
    ),
    prefix="/warehouses",
)
api_router.include_router(
    build_crud_router(
        model=Employee,
        create_schema=e.EmployeeCreate,
        update_schema=e.EmployeeUpdate,
        out_schema=e.EmployeeOut,
        entity_type="employee",
        tags=["employees"],
        write_role=Role.MANAGER,
        search_fields=("name", "code", "role_title"),
    ),
    prefix="/employees",
)
api_router.include_router(
    build_crud_router(
        model=Inventory,
        create_schema=e.InventoryCreate,
        update_schema=e.InventoryUpdate,
        out_schema=e.InventoryOut,
        entity_type="inventory",
        tags=["inventory"],
        search_fields=(),
    ),
    prefix="/inventory",
)
