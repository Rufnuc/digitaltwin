# API

Versioned under `/api/v1`. Interactive docs at `/docs` (Swagger) when the API is
running. Auth is a Bearer JWT obtained from `/auth/login`.

## Auth & RBAC

Roles (most → least privileged): `ADMIN, OWNER, MANAGER, ANALYST, STAFF, VIEWER`.
Checks are **hierarchical** (`role_at_least`). Guard summary:

| Action | Minimum role |
|---|---|
| Read any resource | any authenticated user (VIEWER) |
| Create/update customers, products, suppliers, expenses, inventory, invoices | STAFF |
| Create/update branches, employees | MANAGER |
| Delete a resource | MANAGER |
| Create/run a simulation | ANALYST |
| Create users | ADMIN |

## Endpoints (Phase 1)

```
POST   /auth/login                      → { access_token, role }
GET    /auth/me
POST   /auth/users                      (ADMIN)

GET    /dashboard/summary               KPIs + demo-only flag
GET    /dashboard/revenue-timeseries
GET    /dashboard/alerts

GET    /customers   /suppliers   /products   /expenses   /branches
GET    /employees   /inventory                     (list: ?limit&offset&q)
GET    /{resource}/{id}
POST   /{resource}                      (role-gated)
PATCH  /{resource}/{id}                 (role-gated)
DELETE /{resource}/{id}                 (role-gated)

GET    /invoices  ?customer_id          (with lines)
GET    /invoices/{id}
POST   /invoices                        (STAFF; arithmetic-validated)

GET    /simulations
POST   /simulations                     (ANALYST)
GET    /simulations/{id}
POST   /simulations/{id}/run            (ANALYST)
GET    /simulations/scenario-types

GET    /meta/data-origins               the provenance vocabulary
GET    /audit-logs
GET    /health                          (unauthenticated)
```

## Conventions

- List endpoints return `{ items, total, limit, offset }`; default limit 25,
  max 200. Never dump whole datasets (spec §44).
- Records created via the API are `data_origin = REAL` (user-entered), distinct
  from seeded `DEMO`.
- Invoice creation recomputes subtotal/total and **validates** line arithmetic;
  inconsistent lines set `verification_status = NEEDS_REVIEW` and are **not**
  silently corrected (spec §13).
