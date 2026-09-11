"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import React, { useEffect, useState } from "react";
import { clearSession, getRole, getToken } from "@/lib/api";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/analytics", label: "Analytics" },
  { href: "/data-quality", label: "Data Quality" },
  { href: "/imports", label: "Imports" },
  { href: "/customers", label: "Customers" },
  { href: "/products", label: "Products" },
  { href: "/suppliers", label: "Suppliers" },
  { href: "/invoices", label: "Invoices" },
  { href: "/inventory", label: "Inventory" },
  { href: "/expenses", label: "Expenses" },
  { href: "/simulations", label: "Simulations" },
];

// Later phases (rendered disabled to show the roadmap without pretending to work).
const FUTURE = ["Market Intelligence", "AI Assistant", "Documents"];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setRole(getRole());
    setReady(true);
  }, [router]);

  if (!ready) return <div className="p-8 text-sm text-muted">Loading…</div>;

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 flex-col border-r border-line bg-paper">
        <div className="border-b border-line px-4 py-4">
          <div className="text-sm font-semibold">DigitalTwin</div>
          <div className="text-[11px] text-muted">Business Decision Support</div>
        </div>
        <nav className="flex-1 p-2">
          {NAV.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`block rounded px-3 py-2 text-sm ${
                  active ? "bg-ink text-paper" : "text-ink hover:bg-wash"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
          <div className="mt-4 px-3 text-[10px] uppercase tracking-wide text-muted">
            Later phases
          </div>
          {FUTURE.map((label) => (
            <div key={label} className="cursor-not-allowed px-3 py-2 text-sm text-line">
              {label}
            </div>
          ))}
        </nav>
        <div className="border-t border-line p-3 text-xs">
          <div className="mb-2 text-muted">
            Role: <span className="font-mono text-ink">{role}</span>
          </div>
          <button
            onClick={() => {
              clearSession();
              router.replace("/login");
            }}
            className="w-full rounded border border-line px-2 py-1 hover:bg-wash"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="flex-1 bg-wash">
        <div className="mx-auto max-w-6xl p-6">{children}</div>
      </main>
    </div>
  );
}

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-4">
      <h1 className="text-xl font-semibold">{title}</h1>
      {subtitle && <p className="text-sm text-muted">{subtitle}</p>}
    </div>
  );
}
