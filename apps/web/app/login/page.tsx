"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setSession } from "@/lib/api";

const DEMO_ACCOUNTS = [
  ["owner@demo.example.com", "owner12345", "Owner"],
  ["admin@demo.example.com", "admin12345", "Admin"],
  ["salesgirl@demo.example.com", "sales12345", "Salesgirl"],
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("owner@demo.example.com");
  const [password, setPassword] = useState("owner12345");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.login(email, password);
      setSession(res.access_token, res.role);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-wash p-6">
      <div className="w-full max-w-sm rounded-lg border border-line bg-paper p-6">
        <div className="mb-1 text-lg font-semibold">DigitalTwin</div>
        <div className="mb-6 text-sm text-muted">Sign in to the decision-support platform</div>
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-muted">Email</label>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              className="w-full rounded border border-line px-3 py-2 text-sm outline-none focus:border-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Password</label>
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              className="w-full rounded border border-line px-3 py-2 text-sm outline-none focus:border-ink"
            />
          </div>
          {error && <div className="text-sm text-red-700">{error}</div>}
          <button
            disabled={busy}
            className="w-full rounded bg-ink px-3 py-2 text-sm font-medium text-paper disabled:opacity-50"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <div className="mt-6 border-t border-line pt-4">
          <div className="mb-2 text-[11px] uppercase tracking-wide text-muted">Demo accounts</div>
          <div className="grid grid-cols-2 gap-2">
            {DEMO_ACCOUNTS.map(([em, pw, label]) => (
              <button
                key={em}
                onClick={() => {
                  setEmail(em);
                  setPassword(pw);
                }}
                className="rounded border border-line px-2 py-1 text-xs hover:bg-wash"
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
