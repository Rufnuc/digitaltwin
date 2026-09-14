"use client";
import Link from "next/link";
import { getRole } from "@/lib/api";
import { roleAtLeast } from "@/lib/roles";

// Shared sub-navigation for the inventory area, so stock, warehouses and the
// legacy levels view read as one place.
const TABS = [
  { href: "/stock", label: "Stock & Markers", key: "stock" },
  { href: "/warehouses", label: "Warehouses", key: "warehouses", minRole: "MANAGER" as const },
  { href: "/inventory", label: "Levels", key: "levels" },
];

export function InventoryTabs({ active }: { active: "stock" | "warehouses" | "levels" }) {
  const role = getRole();
  const tabs = TABS.filter((t) => !t.minRole || roleAtLeast(role, t.minRole));
  return (
    <div className="mb-4 flex gap-1 overflow-x-auto border-b border-line">
      {tabs.map((t) => (
        <Link
          key={t.key}
          href={t.href}
          className={`-mb-px shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-sm ${
            active === t.key ? "border-ink font-medium" : "border-transparent text-muted hover:text-ink"
          }`}
        >
          {t.label}
        </Link>
      ))}
    </div>
  );
}
