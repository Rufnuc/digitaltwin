// Mirrors the backend RBAC ordering (least → most privileged). SALESGIRL is a
// restricted front-desk role that sits below STAFF; its page access is an explicit
// allowlist (see Shell.tsx), not a hierarchy tier.
// OWNER is the top role (outranks ADMIN), matching the backend ROLE_ORDER.
export const ROLE_ORDER = ["VIEWER", "SALESGIRL", "STAFF", "ANALYST", "MANAGER", "ADMIN", "OWNER"] as const;
export type Role = (typeof ROLE_ORDER)[number];

// Pages the SALESGIRL front-desk role may open. Everything else is hidden.
export const SALESGIRL_PAGES = new Set<string>([
  "/dashboard", "/customers", "/invoices", "/waybills", "/products", "/assistant", "/settings",
]);
export const isSalesgirl = (role: string | null | undefined) => role === "SALESGIRL";

export function roleAtLeast(actual: string | null | undefined, required: Role): boolean {
  const a = ROLE_ORDER.indexOf((actual as Role) ?? "VIEWER");
  const r = ROLE_ORDER.indexOf(required);
  if (a < 0) return false;
  return a >= r;
}
