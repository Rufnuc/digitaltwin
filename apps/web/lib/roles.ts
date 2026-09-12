// Mirrors the backend RBAC ordering (least → most privileged).
export const ROLE_ORDER = ["VIEWER", "STAFF", "ANALYST", "MANAGER", "OWNER", "ADMIN"] as const;
export type Role = (typeof ROLE_ORDER)[number];

export function roleAtLeast(actual: string | null | undefined, required: Role): boolean {
  const a = ROLE_ORDER.indexOf((actual as Role) ?? "VIEWER");
  const r = ROLE_ORDER.indexOf(required);
  if (a < 0) return false;
  return a >= r;
}
