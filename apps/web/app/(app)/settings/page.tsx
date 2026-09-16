"use client";
import { useEffect, useState } from "react";
import { api, getRole, type DataStats, type UserRow } from "@/lib/api";
import { PageHeader } from "@/components/Shell";
import { Card, ResponsiveTable } from "@/components/ui";
import { num } from "@/lib/format";
import { roleAtLeast } from "@/lib/roles";
import { getStoredTheme, setTheme, type Theme } from "@/lib/theme";

const ROLES = ["VIEWER", "STAFF", "ANALYST", "MANAGER", "OWNER", "ADMIN"];

export default function SettingsPage() {
  const [theme, setThemeState] = useState<Theme>("system");
  const [me, setMe] = useState<{ email: string; full_name: string; role: string } | null>(null);
  const role = getRole();
  const isAdmin = roleAtLeast(role, "ADMIN");
  const isOwner = roleAtLeast(role, "OWNER");

  useEffect(() => {
    setThemeState(getStoredTheme());
    api.me().then(setMe).catch(() => {});
  }, []);

  function chooseTheme(t: Theme) {
    setThemeState(t);
    setTheme(t);
  }

  return (
    <div>
      <PageHeader title="Settings" subtitle="Appearance, your account, and administration." />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <div className="mb-3 text-sm font-medium">Appearance</div>
          <div className="mb-2 text-xs text-muted">Theme</div>
          <div className="flex gap-2">
            {(["light", "dark", "system"] as Theme[]).map((t) => (
              <button
                key={t}
                onClick={() => chooseTheme(t)}
                className={`rounded border px-3 py-1.5 text-sm capitalize ${
                  theme === t ? "border-ink bg-ink text-paper" : "border-line hover:bg-wash"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </Card>

        <Card className="p-4">
          <div className="mb-3 text-sm font-medium">Account</div>
          {me ? (
            <div className="space-y-1 text-sm">
              <div>
                <span className="text-muted">Name:</span> {me.full_name}
              </div>
              <div>
                <span className="text-muted">Email:</span> {me.email}
              </div>
              <div>
                <span className="text-muted">Role:</span>{" "}
                <span className="font-mono">{me.role}</span>
              </div>
            </div>
          ) : (
            <div className="text-sm text-muted">Loading…</div>
          )}
        </Card>
      </div>

      {isOwner && <CompanyPanel />}
      {isAdmin && <UsersPanel />}
      {isOwner && <DataPanel />}
    </div>
  );
}

function CompanyPanel() {
  const FIELDS: { key: string; label: string }[] = [
    { key: "name", label: "Company name" },
    { key: "address", label: "Address" },
    { key: "phone", label: "Phone" },
    { key: "email", label: "Email" },
    { key: "website", label: "Website" },
    { key: "tax_id", label: "Tax ID / RC number" },
    { key: "footer_note", label: "Invoice footer note" },
  ];
  const [form, setForm] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .company()
      .then((c) => {
        const f: Record<string, string> = {};
        for (const k of FIELDS) f[k.key] = (c as unknown as Record<string, string>)[k.key] ?? "";
        setForm(f);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save() {
    setMsg(null);
    setError(null);
    try {
      await api.updateCompany(form);
      setMsg("Company details saved — they now appear on printed invoices.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    }
  }

  return (
    <Card className="mt-4 p-4">
      <div className="mb-1 text-sm font-medium">Company details</div>
      <div className="mb-3 text-xs text-muted">Printed on invoices and documents.</div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {FIELDS.map((f) => (
          <label key={f.key} className="text-xs text-muted">
            {f.label}
            <input
              value={form[f.key] ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
              className="mt-1 w-full rounded border border-line bg-paper px-3 py-1.5 text-sm outline-none focus:border-ink"
            />
          </label>
        ))}
      </div>
      {error && <div className="mt-2 text-sm text-red-700">{error}</div>}
      {msg && <div className="mt-2 text-sm text-green-700 dark:text-green-300">{msg}</div>}
      <button onClick={save} className="mt-3 rounded bg-ink px-3 py-1.5 text-sm font-medium text-paper">
        Save
      </button>
    </Card>
  );
}

function UsersPanel() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ email: "", full_name: "", password: "", role: "STAFF" });
  const [busy, setBusy] = useState(false);

  const load = () => api.listUsers().then(setUsers).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  async function change(id: number, body: Record<string, unknown>) {
    try {
      await api.updateUser(id, body);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    }
  }

  async function resetPassword(id: number, name: string) {
    const pw = window.prompt(`New password for ${name} (min 8 characters):`);
    if (!pw) return;
    if (pw.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    await change(id, { password: pw });
    setError(null);
    window.alert("Password updated.");
  }

  async function create() {
    setBusy(true);
    setError(null);
    try {
      await api.createUser(form);
      setForm({ email: "", full_name: "", password: "", role: "STAFF" });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mt-4 p-4">
      <div className="mb-3 text-sm font-medium">User management</div>
      {error && <div className="mb-2 text-sm text-red-700">{error}</div>}
      <ResponsiveTable
        headers={["Name", "Email", "Role", "Active", "Actions"]}
        empty="No users."
        rows={users.map((u) => [
          u.full_name,
          <span className="text-muted">{u.email}</span>,
          <select
            value={u.role}
            onChange={(e) => change(u.id, { role: e.target.value })}
            className="rounded border border-line bg-paper px-2 py-1 text-xs"
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>,
          <button
            onClick={() => change(u.id, { is_active: !u.is_active })}
            className={`rounded border px-2 py-1 text-xs ${
              u.is_active
                ? "border-green-500/40 bg-green-500/15 text-green-700 dark:text-green-300"
                : "border-line text-muted"
            }`}
          >
            {u.is_active ? "Active" : "Inactive"}
          </button>,
          <span className="flex gap-1">
            <button
              onClick={() => resetPassword(u.id, u.full_name || u.email)}
              className="rounded border border-line px-2 py-1 text-xs hover:bg-wash"
            >
              Reset password
            </button>
            <a
              href={`/activity?user=${u.id}`}
              className="rounded border border-line px-2 py-1 text-xs hover:bg-wash"
            >
              Activity
            </a>
          </span>,
        ])}
      />

      <div className="mt-3 flex flex-wrap items-end gap-2">
        <Inp label="Full name" v={form.full_name} on={(v) => setForm({ ...form, full_name: v })} />
        <Inp label="Email" v={form.email} on={(v) => setForm({ ...form, email: v })} />
        <Inp label="Password" v={form.password} on={(v) => setForm({ ...form, password: v })} type="password" />
        <div>
          <label className="mb-1 block text-xs text-muted">Role</label>
          <select
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
            className="rounded border border-line bg-paper px-2 py-1.5 text-sm"
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={create}
          disabled={busy || !form.email || !form.password}
          className="rounded bg-ink px-3 py-2 text-sm font-medium text-paper disabled:opacity-50"
        >
          Add user
        </button>
      </div>
    </Card>
  );
}

function DataPanel() {
  const [stats, setStats] = useState<DataStats | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => api.dataStats().then(setStats).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  async function purge() {
    setError(null);
    setMsg(null);
    try {
      const r = await api.purgeDemo();
      setMsg(`${r.message} (${r.total_deleted} rows removed)`);
      setConfirming(false);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Purge failed");
    }
  }

  return (
    <Card className="mt-4 p-4">
      <div className="mb-3 text-sm font-medium">Data management</div>
      {stats && (
        <div className="mb-3 overflow-x-auto rounded border border-line">
          <table className="min-w-full text-sm">
            <thead className="bg-wash text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                {["Table", "Total", "Demo", "Real"].map((h) => (
                  <th key={h} className="px-3 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {stats.tables.map((t) => (
                <tr key={t.table} className="border-t border-line tabular-nums">
                  <td className="px-3 py-1.5 font-mono text-xs">{t.table}</td>
                  <td className="px-3 py-1.5">{num(t.total)}</td>
                  <td className="px-3 py-1.5 text-yellow-700">{num(t.demo)}</td>
                  <td className="px-3 py-1.5 text-green-700">{num(t.real)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mb-2 text-xs text-muted">
        Removing demo data deletes only rows tagged DEMO — your real and imported data is untouched.
        This is how you start a clean slate before entering real business data.
      </p>
      {!confirming ? (
        <button
          onClick={() => setConfirming(true)}
          className="rounded border border-red-500/40 bg-red-500/15 px-3 py-2 text-sm text-red-700 dark:text-red-300 hover:bg-red-500/150/25"
        >
          Delete all demo data…
        </button>
      ) : (
        <div className="flex items-center gap-2">
          <span className="text-sm text-red-700 dark:text-red-300">
            This permanently deletes {stats ? num(stats.total_demo_rows) : ""} demo rows. Sure?
          </span>
          <button
            onClick={purge}
            className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white"
          >
            Yes, delete demo data
          </button>
          <button
            onClick={() => setConfirming(false)}
            className="rounded border border-line px-3 py-1.5 text-sm hover:bg-wash"
          >
            Cancel
          </button>
        </div>
      )}
      {msg && <div className="mt-2 text-sm text-green-700 dark:text-green-300">{msg}</div>}
      {error && <div className="mt-2 text-sm text-red-700">{error}</div>}
    </Card>
  );
}

function Inp({
  label,
  v,
  on,
  type = "text",
}: {
  label: string;
  v: string;
  on: (v: string) => void;
  type?: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-muted">{label}</label>
      <input
        type={type}
        value={v}
        onChange={(e) => on(e.target.value)}
        className="rounded border border-line bg-paper px-2 py-1.5 text-sm outline-none focus:border-ink"
      />
    </div>
  );
}
