import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, newIdempotencyKey } from "../api";

// Capture the headers of each outgoing request so we can assert the
// Idempotency-Key plumbing without a real backend.
function mockFetch() {
  const calls: { url: string; headers: Record<string, string> }[] = [];
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, headers: (init.headers ?? {}) as Record<string, string> });
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}

describe("newIdempotencyKey", () => {
  it("returns unique, non-empty keys", () => {
    const keys = new Set(Array.from({ length: 100 }, () => newIdempotencyKey()));
    expect(keys.size).toBe(100);
    for (const k of keys) expect(k.length).toBeGreaterThan(8);
  });
});

describe("idempotency header plumbing", () => {
  beforeEach(() => {
    try {
      window.localStorage.clear();
    } catch {
      /* ignore */
    }
  });
  afterEach(() => vi.unstubAllGlobals());

  it("sends the Idempotency-Key header on recordPayment", async () => {
    const calls = mockFetch();
    const key = newIdempotencyKey();
    await api.recordPayment(42, { amount: 100, method: "cash" }, key);
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain("/receivables/invoices/42/payments");
    expect(calls[0].headers["Idempotency-Key"]).toBe(key);
  });

  it("sends the Idempotency-Key header on invoiceSell", async () => {
    const calls = mockFetch();
    const key = newIdempotencyKey();
    await api.invoiceSell({ invoice_number: "T-1" }, key);
    expect(calls[0].headers["Idempotency-Key"]).toBe(key);
  });

  it("reuses the same key across a retry (double-submit is one logical write)", async () => {
    const calls = mockFetch();
    const key = newIdempotencyKey();
    // Simulate the UI retrying the SAME submission (same key held by the form).
    await api.recordPayment(7, { amount: 50, method: "cash" }, key);
    await api.recordPayment(7, { amount: 50, method: "cash" }, key);
    expect(calls).toHaveLength(2);
    expect(calls[0].headers["Idempotency-Key"]).toBe(key);
    expect(calls[1].headers["Idempotency-Key"]).toBe(key); // identical → backend dedups
  });

  it("omits the header when no key is given", async () => {
    const calls = mockFetch();
    await api.recordPayment(1, { amount: 1, method: "cash" });
    expect(calls[0].headers["Idempotency-Key"]).toBeUndefined();
  });
});
