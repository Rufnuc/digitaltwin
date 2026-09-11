// Shared epistemic-status vocabulary (mirrors apps/api/app/core/enums.py).
// Single source of truth for TS consumers across the monorepo.
export const DATA_ORIGINS = [
  "REAL", "DEMO", "ESTIMATED", "MISSING",
  "ASSUMPTION", "MODEL_OUTPUT", "FORECAST", "AI_INTERPRETATION",
] as const;
export type DataOrigin = (typeof DATA_ORIGINS)[number];

export const ROLES = ["ADMIN", "OWNER", "MANAGER", "ANALYST", "STAFF", "VIEWER"] as const;
export type Role = (typeof ROLES)[number];
