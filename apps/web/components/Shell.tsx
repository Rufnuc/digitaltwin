"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import React, { useEffect, useState } from "react";
import { api, clearSession, getRole, getToken, setSession } from "@/lib/api";
import { NotificationBell } from "@/components/NotificationBell";
import { type Role, roleAtLeast } from "@/lib/roles";
import { getStoredTheme, resolveDark, setTheme } from "@/lib/theme";

// minRole gates a nav item to the user's tier (undefined = everyone). Items are
// grouped into labelled sections so the sidebar reads as a structured menu.
type NavItem = { href: string; label: string; minRole?: Role };
type NavSection = { header?: string; items: NavItem[] };

const NAV: NavSection[] = [
  {
    items: [
      { href: "/dashboard", label: "Dashboard" },
      { href: "/analytics", label: "Analytics" },
      { href: "/data-quality", label: "Data Quality" },
    ],
  },
  {
    header: "Sales",
    items: [
      { href: "/customers", label: "Customers" },
      // Invoices covers recording sales and the New Sale flow (via its button).
      { href: "/invoices", label: "Invoices & Sales" },
    ],
  },
  {
    header: "Inventory",
    items: [
      { href: "/products", label: "Products" },
      { href: "/suppliers", label: "Suppliers" },
      // One entry for the whole inventory area — stock, warehouses and levels
      // share a tab strip once inside.
      { href: "/stock", label: "Inventory", minRole: "STAFF" },
      { href: "/expenses", label: "Expenses" },
    ],
  },
  {
    header: "Intelligence",
    items: [
      { href: "/market", label: "Market Intel" },
      { href: "/shipping", label: "Shipping" },
      { href: "/impact", label: "News → Impact", minRole: "ANALYST" },
      { href: "/simulations", label: "Simulations", minRole: "ANALYST" },
      { href: "/agents", label: "Digital Twin", minRole: "ANALYST" },
      { href: "/assistant", label: "Benfieg (AI)" },
    ],
  },
  {
    header: "Data & Settings",
    items: [
      { href: "/imports", label: "Imports", minRole: "STAFF" },
      { href: "/documents", label: "Documents", minRole: "STAFF" },
      { href: "/settings", label: "Settings" },
    ],
  },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [role, setRole] = useState<string | null>(null);
  const [open, setOpen] = useState(true);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setRole(getRole());
    setDark(resolveDark(getStoredTheme()));
    // Restore last menu state; default open on wide screens, closed on narrow.
    let initial = true;
    try {
      const saved = window.localStorage.getItem("dt_menu_open");
      initial = saved != null ? saved === "1" : window.innerWidth >= 768;
    } catch {
      /* ignore */
    }
    setOpen(initial);
    setReady(true);
  }, [router]);

  // Silent session keep-alive: refresh the token now (covers a reopened tab) and
  // every 20 min while the app is open, so an active session never expires.
  useEffect(() => {
    if (!getToken()) return;
    const doRefresh = () =>
      api
        .refresh()
        .then((r) => setSession(r.access_token, r.role))
        .catch(() => {
          /* an expired token can't refresh; the 401 handler routes to login */
        });
    doRefresh();
    const t = setInterval(doRefresh, 20 * 60 * 1000);
    return () => clearInterval(t);
  }, []);

  function toggle() {
    setOpen((v) => {
      const next = !v;
      try {
        window.localStorage.setItem("dt_menu_open", next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  function toggleTheme() {
    const next = !dark;
    setDark(next);
    setTheme(next ? "dark" : "light");
  }

  if (!ready) return <div className="p-8 text-sm text-muted">Loading…</div>;

  // Filter each section's items by role, then drop any section left empty.
  const nav = NAV.map((section) => ({
    ...section,
    items: section.items.filter((item) => !item.minRole || roleAtLeast(role, item.minRole)),
  })).filter((section) => section.items.length > 0);

  return (
    <div className="min-h-screen bg-wash">
      {/* Top bar with the menu toggle — always visible */}
      <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-line bg-paper px-3">
        <button
          onClick={toggle}
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          className="flex h-8 w-8 items-center justify-center rounded border border-line hover:bg-wash"
        >
          <span className="text-lg leading-none">{open ? "✕" : "☰"}</span>
        </button>
        <div className="text-sm font-semibold">DigitalTwin</div>
        <div className="hidden text-[11px] text-muted sm:block">Business Decision Support</div>
        <div className="ml-auto flex items-center gap-3">
          <NotificationBell />
          <button
            onClick={toggleTheme}
            aria-label="Toggle dark mode"
            title={dark ? "Switch to light" : "Switch to dark"}
            className="flex h-8 w-8 items-center justify-center rounded border border-line hover:bg-wash"
          >
            <span className="text-sm leading-none">{dark ? "☀️" : "🌙"}</span>
          </button>
          <span className="font-mono text-[11px] text-muted">{role}</span>
        </div>
      </header>

      {/* Backdrop (mobile) when open */}
      {open && (
        <div
          onClick={toggle}
          className="fixed inset-0 top-12 z-10 bg-black/20 md:hidden"
          aria-hidden
        />
      )}

      {/* Sidebar — slides in/out */}
      <aside
        className={`fixed left-0 top-12 z-20 flex h-[calc(100vh-3rem)] w-60 transform flex-col border-r border-line bg-paper transition-transform duration-200 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <nav className="flex-1 overflow-y-auto p-2">
          {nav.map((section, si) => (
            <div key={section.header ?? si} className={si > 0 ? "mt-3" : ""}>
              {section.header && (
                <div className="px-3 pb-1 pt-1 text-[10px] font-medium uppercase tracking-wider text-muted">
                  {section.header}
                </div>
              )}
              {section.items.map((item) => {
                const active = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => {
                      if (window.innerWidth < 768) toggle();
                    }}
                    className={`block rounded px-3 py-2 text-sm ${
                      active ? "bg-ink text-paper" : "text-ink hover:bg-wash"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="border-t border-line p-3 text-xs">
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

      {/* Content — shifts right when the menu is open on desktop */}
      <main className={`transition-all duration-200 ${open ? "md:ml-60" : "ml-0"}`}>
        <div className="mx-auto max-w-6xl p-4 sm:p-6">{children}</div>
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
