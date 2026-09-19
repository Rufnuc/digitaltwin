// Minimal typed API client. Token is held in localStorage (Phase 1 dev auth).
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const V1 = `${BASE}/api/v1`;

// Resolve an image_url for use in <img src>: app paths ("/api/v1/...") are made
// absolute against the API host; external URLs pass through unchanged.
export function imageSrc(url: string | null | undefined): string | null {
  if (!url) return null;
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  return `${BASE}${url.startsWith("/") ? "" : "/"}${url}`;
}

const TOKEN_KEY = "dt_token";
const ROLE_KEY = "dt_role";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setSession(token: string, role: string) {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
    window.localStorage.setItem(ROLE_KEY, role);
  } catch {
    /* ignore */
  }
}

export function getRole(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(ROLE_KEY);
  } catch {
    return null;
  }
}

export function clearSession() {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(ROLE_KEY);
  } catch {
    /* ignore */
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// A fresh idempotency key per submit action. The same key is reused across retries
// of one logical submission (so a lost-response retry is safe) and regenerated after
// a success, so the backend records exactly one write per action.
export function newIdempotencyKey(): string {
  try {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  } catch {
    /* fall through */
  }
  return `idem-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${V1}${path}`, { ...init, headers });
  if (!res.ok) {
    if (res.status === 401) onUnauthorized(path);
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// On an expired/invalid session, clear it and send the user to login — once,
// and never for a failed login attempt (wrong password is not a dead session).
function onUnauthorized(path: string) {
  if (path.includes("/auth/login")) return;
  clearSession();
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    window.location.href = "/login";
  }
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; role: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<{ id: number; email: string; full_name: string; role: string }>("/auth/me"),
  refresh: () =>
    request<{ access_token: string; role: string }>("/auth/refresh", { method: "POST" }),
  dashboardSummary: () => request<DashboardSummary>("/dashboard/summary"),
  revenueSeries: () =>
    request<{ series: { period: string; revenue: number }[] }>("/dashboard/revenue-timeseries"),
  alerts: () => request<{ items: AlertItem[] }>("/dashboard/alerts"),
  list: <T>(resource: string, params = "") =>
    request<{ items: T[]; total: number; limit: number; offset: number }>(
      `/${resource}${params}`,
    ),
  // Generic CRUD writes against build_crud_router resources.
  createResource: <T>(resource: string, body: unknown, idempotencyKey?: string) =>
    request<T>(`/${resource}`, {
      method: "POST",
      body: JSON.stringify(body),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    }),
  updateResource: <T>(resource: string, id: number | string, body: unknown) =>
    request<T>(`/${resource}/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteResource: (resource: string, id: number | string) =>
    request<{ deleted: boolean } | Record<string, unknown>>(`/${resource}/${id}`, {
      method: "DELETE",
    }),
  // ---- Warehouses & stock ----
  stockLots: (params = "") => request<{ items: StockLot[]; total: number }>(`/stock/lots${params}`),
  stockLot: (id: number) => request<StockLotDetail>(`/stock/lots/${id}`),
  productOnHand: (productId: number) =>
    request<{ product_id: number; by_warehouse: { warehouse_id: number; warehouse: string; on_hand: number }[] }>(
      `/stock/products/${productId}/on-hand`,
    ),
  stockReceive: (body: unknown) =>
    request<StockLotDetail>("/stock/receive", { method: "POST", body: JSON.stringify(body) }),
  stockReceiveBatch: (body: unknown) =>
    request<{ received: number; lots: { lot_code: string; product_id: number; quantity: number }[] }>(
      "/stock/receive-batch",
      { method: "POST", body: JSON.stringify(body) },
    ),
  stockTransfer: (body: unknown) =>
    request<Record<string, unknown>>("/stock/transfer", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  stockAdjust: (body: unknown) =>
    request<StockLotDetail>("/stock/adjust", { method: "POST", body: JSON.stringify(body) }),
  invoiceSell: (body: unknown, idempotencyKey?: string) =>
    request<{ invoice: Record<string, unknown>; allocations: unknown[]; note: string }>(
      "/invoices/sell",
      {
        method: "POST",
        body: JSON.stringify(body),
        headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
      },
    ),
  // ---- Waybills (dispatch) ----
  listWaybills: (params = "") =>
    request<{ items: Waybill[]; total: number; limit: number; offset: number }>(
      `/waybills${params}`,
    ),
  getWaybill: (id: number) => request<Waybill>(`/waybills/${id}`),
  createWaybill: (body: unknown) =>
    request<Waybill>("/waybills", { method: "POST", body: JSON.stringify(body) }),
  updateWaybill: (id: number, body: unknown) =>
    request<Waybill>(`/waybills/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  // ---- Procurement (supplier requests → orders → receiving) ----
  listPurchases: (params = "") =>
    request<{ items: Purchase[]; total: number; limit: number; offset: number }>(
      `/purchases${params}`,
    ),
  getPurchase: (id: number) => request<Purchase>(`/purchases/${id}`),
  createRequest: (body: unknown) =>
    request<Purchase>("/purchases", { method: "POST", body: JSON.stringify(body) }),
  setPurchaseStatus: (id: number, status: string) =>
    request<Purchase>(`/purchases/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  receivePurchase: (id: number, body: unknown) =>
    request<Purchase>(`/purchases/${id}/receive`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  invoiceDetail: (id: number) => request<InvoiceDetail>(`/invoices/${id}`),
  invoiceVersions: (id: number) =>
    request<{ items: InvoiceVersionRow[] }>(`/invoices/${id}/versions`),
  invoiceUpdate: (id: number, body: unknown) =>
    request<InvoiceDetail>(`/invoices/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  productImages: (id: number) =>
    request<{ items: ProductImage[] }>(`/products/${id}/images`),
  productHistory: (id: number) => request<ProductHistory>(`/products/${id}/history`),
  supplierTrace: (id: number) => request<SupplierTrace>(`/suppliers/${id}/trace`),
  addProductImageUrl: (id: number, url: string) =>
    request<ProductImage>(`/products/${id}/image-url`, { method: "POST", body: JSON.stringify({ url }) }),
  setPrimaryImage: (id: number, imageId: number) =>
    request<{ ok: boolean; image_url: string }>(`/products/${id}/images/${imageId}/primary`, { method: "POST" }),
  deleteProductImage: (id: number, imageId: number) =>
    request<{ ok: boolean }>(`/products/${id}/images/${imageId}`, { method: "DELETE" }),
  uploadProductImage: async (id: number, file: File): Promise<ProductImage> => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${V1}/products/${id}/image`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
      body: fd,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const b = await res.json();
        detail = typeof b.detail === "string" ? b.detail : detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(res.status, detail);
    }
    return res.json();
  },
  company: () => request<CompanyProfile>("/company"),
  updateCompany: (body: unknown) =>
    request<CompanyProfile>("/company", { method: "PUT", body: JSON.stringify(body) }),
  scenarioTypes: () => request<{ implemented: string[] }>("/simulations/scenario-types"),
  createSimulation: (body: unknown) =>
    request<Simulation>("/simulations", { method: "POST", body: JSON.stringify(body) }),
  runSimulation: (id: number) =>
    request<Simulation>(`/simulations/${id}/run`, { method: "POST" }),
  listSimulations: () => request<{ items: Simulation[]; total: number }>("/simulations"),
  // Plain-language simulation (auto explore / manual / history).
  runAutoSimulation: () => request<PlainSim>("/simulations/auto", { method: "POST" }),
  runManualSimulation: (body: {
    price_change_percent: number;
    demand_change_percent: number;
    unit_cost_change_percent: number;
  }) => request<PlainSim>("/simulations/manual", { method: "POST", body: JSON.stringify(body) }),
  plainSimulation: (id: number) => request<PlainSim>(`/simulations/${id}/plain`),

  // ---- Phase 3: advanced simulation ----
  monteCarlo: (body: unknown) =>
    request<Simulation>("/simulations/monte-carlo", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  sensitivity: (body: unknown) =>
    request<Tornado>("/simulations/sensitivity", { method: "POST", body: JSON.stringify(body) }),
  compare: (scenarios: unknown[]) =>
    request<Comparison>("/simulations/compare", {
      method: "POST",
      body: JSON.stringify({ scenarios }),
    }),

  // ---- Phase 4: AI assistant ----
  assistantAsk: (question: string, conversationId?: number, signal?: AbortSignal) =>
    request<AssistantResponse>("/assistant/ask", {
      method: "POST",
      body: JSON.stringify({ question, conversation_id: conversationId ?? null }),
      signal,
    }),
  assistantTools: () => request<{ tools: AssistantTool[] }>("/assistant/tools"),
  // Execute a previously-proposed assistant write (two-step confirm-gating).
  assistantConfirm: (confirmationToken: string) =>
    request<{ executed: string; result: Record<string, unknown> }>("/assistant/confirm", {
      method: "POST",
      body: JSON.stringify({ confirmation_token: confirmationToken }),
    }),
  // Benfieg chat history (per user).
  listConversations: () =>
    request<{ items: ConversationSummary[] }>("/assistant/conversations"),
  getConversation: (id: number) =>
    request<ConversationDetail>(`/assistant/conversations/${id}`),
  renameConversation: (id: number, title: string) =>
    request<{ ok: boolean }>(`/assistant/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  deleteConversation: (id: number) =>
    request<{ ok: boolean }>(`/assistant/conversations/${id}`, { method: "DELETE" }),
  // Local, offline Whisper transcription of recorded mic audio (16 kHz mono WAV).
  assistantTranscribe: async (
    wav: Blob,
    signal?: AbortSignal,
  ): Promise<{ text: string; language: string | null; model: string }> => {
    const fd = new FormData();
    fd.append("file", wav, "voice.wav");
    const res = await fetch(`${V1}/assistant/transcribe`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
      body: fd,
      signal,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const b = await res.json();
        detail = typeof b.detail === "string" ? b.detail : detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(res.status, detail);
    }
    return res.json();
  },

  // ---- Phase 5: documents / OCR ingestion ----
  uploadDocument: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return requestForm<{ document: DocumentItem; extraction: Extraction }>("/documents", fd);
  },
  listDocuments: () => request<{ items: DocumentItem[] }>("/documents"),
  reviewQueue: (status?: string) =>
    request<{ items: Extraction[] }>(`/extractions${status ? `?status=${status}` : ""}`),
  approveExtraction: (id: number, corrections: Record<string, unknown> = {}) =>
    request<{ invoice_id: number; extraction: Extraction }>(`/extractions/${id}/approve`, {
      method: "POST",
      body: JSON.stringify(corrections),
    }),
  rejectExtraction: (id: number, notes?: string) =>
    request<Extraction>(`/extractions/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ notes }),
    }),

  // ---- Phase 6: market intelligence ----
  marketSummary: () => request<MarketSummary>("/market/summary"),
  marketIndicators: () => request<{ items: MarketIndicator[] }>("/market/indicators"),
  marketEvents: (minRelevance = 0) =>
    request<{ items: MarketNews[] }>(`/market/events?min_relevance=${minRelevance}&limit=30`),
  refreshMarket: () => request<MarketRefreshResult>("/market/refresh", { method: "POST" }),

  // ---- Phase 7: news -> business impact ----
  impactScan: (createAlerts = true, assumptions: Record<string, number> = {}) =>
    request<ImpactScanResult>("/impact/scan", {
      method: "POST",
      body: JSON.stringify({ create_alerts: createAlerts, assumptions }),
    }),

  // ---- Phase 8: multi-agent digital twin ----
  agentsRoster: () => request<AgentRoster>("/agents/roster"),
  agentSimulate: (body: unknown) =>
    request<AgentSimResult>("/agents/simulate", { method: "POST", body: JSON.stringify(body) }),
  agentCompare: (body: unknown) =>
    request<AgentCompareResult>("/agents/compare", { method: "POST", body: JSON.stringify(body) }),

  // ---- Money: accounts receivable ----
  receivablesSummary: () => request<ReceivablesSummary>("/receivables/summary"),
  overdueReceivables: () => request<OverdueList>("/receivables/overdue"),
  recordPayment: (invoiceId: number, body: unknown, idempotencyKey?: string) =>
    request<Record<string, unknown>>(`/receivables/invoices/${invoiceId}/payments`, {
      method: "POST",
      body: JSON.stringify(body),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    }),
  customerStatement: (customerId: number) =>
    request<CustomerStatement>(`/receivables/customers/${customerId}/statement`),
  cashFlow: (days = 30) => request<CashFlow>(`/cashflow/summary?days=${days}`),
  payablesSummary: () => request<PayablesSummary>("/payables/summary"),
  taxSummary: (params = "") => request<TaxSummary>(`/tax/summary${params}`),

  // ---- Audit trail / activity log ----
  activityLog: (params = "") => request<AuditPage>(`/audit${params}`),
  // Download the (filtered) activity log as a CSV file (admin only).
  exportActivityLog: async (params = ""): Promise<void> => {
    const res = await fetch(`${V1}/audit/export${params}`, {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    });
    if (!res.ok) throw new ApiError(res.status, "Export failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `activity-log-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  entityHistory: (entityType: string, entityId: number) =>
    request<{ entity_type: string; entity_id: number; events: AuditEvent[] }>(
      `/audit/entity/${entityType}/${entityId}`,
    ),

  // ---- Quant: reorder plan (action list) ----
  reorderPlan: (includeDemo = false) =>
    request<ReorderPlan>(`/quant/reorder-plan?include_demo=${includeDemo}`),

  // ---- Notifications ----
  notifications: (unreadOnly = false) =>
    request<{ items: NotificationItem[]; unread_count: number }>(
      `/notifications?unread_only=${unreadOnly}`,
    ),
  unreadCount: () => request<{ unread_count: number }>("/notifications/unread-count"),
  generateNotifications: () =>
    request<{ created: number; categories: string[] }>("/notifications/generate", {
      method: "POST",
    }),
  markNotificationRead: (id: number) =>
    request<{ ok: boolean }>(`/notifications/${id}/read`, { method: "POST" }),
  markAllNotificationsRead: () =>
    request<{ marked_read: number }>("/notifications/read-all", { method: "POST" }),

  // ---- Users & data management (admin) ----
  listUsers: () => request<UserRow[]>("/auth/users"),
  createUser: (body: unknown) =>
    request<UserRow>("/auth/users", { method: "POST", body: JSON.stringify(body) }),
  updateUser: (id: number, body: unknown) =>
    request<UserRow>(`/auth/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  dataStats: () => request<DataStats>("/admin/data-stats"),
  purgeDemo: () => request<PurgeResult>("/admin/purge-demo", { method: "POST" }),

  // ---- Shipping monitor (aisstream) ----
  shippingStatus: () => request<ShippingStatus>("/shipping/status"),
  shippingVessels: (params = "") => request<{ items: Vessel[]; note: string }>(`/shipping/vessels${params}`),
  shippingConditions: () => request<LaneConditions>("/shipping/conditions"),
  shippingArrivals: () =>
    request<{ items: Vessel[]; count: number; note: string }>("/shipping/arrivals"),

  // ---- Phase 2: analytics ----
  analyticsCustomers: () => request<CustomerIntel>("/analytics/customers"),
  analyticsProducts: () => request<ProductIntel>("/analytics/products"),
  analyticsSuppliers: () => request<SupplierIntel>("/analytics/suppliers"),
  financials: () => request<{ series: FinancialRow[] }>("/analytics/financials"),
  dataQuality: () => request<DataQuality>("/analytics/data-quality"),

  // ---- Phase 2: imports ----
  importEntities: () => request<{ entities: Record<string, ImportField[]> }>("/imports/entities"),
  previewImport: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return requestForm<ImportPreview>("/imports/preview", fd);
  },
  commitImport: (entityType: string, mapping: Record<string, string>, file: File) => {
    const fd = new FormData();
    fd.append("entity_type", entityType);
    fd.append("mapping", JSON.stringify(mapping));
    fd.append("file", file);
    return requestForm<ImportResult>("/imports", fd);
  },
  listImports: () => request<{ items: ImportBatch[] }>("/imports"),
};

async function requestForm<T>(path: string, body: FormData): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${V1}${path}`, { method: "POST", body, headers });
  if (!res.ok) {
    if (res.status === 401) onUnauthorized(path);
    let detail = res.statusText;
    try {
      const b = await res.json();
      detail = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

// ---- Types ----
export interface DashboardSummary {
  kpis: {
    revenue: number;
    cogs: number;
    operating_expenses: number;
    gross_profit: number;
    gross_margin: number;
    net_profit: number;
    net_margin: number;
    orders: number;
    units_sold: number;
    active_customers: number;
    inventory_value: number;
  };
  data_status: { total_invoices: number; real_invoices: number; is_demo_only: boolean };
  provenance: string;
}

export interface AlertItem {
  id: number;
  severity: string;
  category: string;
  title: string;
  body: string | null;
  data_origin: string;
}

export interface SimResult {
  metric: string;
  baseline: { value: number } | null;
  scenario: { value: number } | null;
  delta: { absolute: number; percent: number } | null;
  detail: string | null;
}

export interface SimOutcome {
  name: string;
  net_profit: number;
  net_profit_delta: number;
  net_profit_pct: number;
  revenue: number;
  revenue_delta: number;
  verdict: string;
  gross_margin?: number;
}
export interface PlainSim {
  kind: string;
  as_of: string;
  run_id?: number;
  baseline: { net_profit: number; revenue: number; gross_margin?: number };
  best?: string;
  worst?: string;
  outcomes?: SimOutcome[];
  inputs?: Record<string, number>;
  result?: SimOutcome;
  note?: string;
}

export interface Simulation {
  id: number;
  name: string;
  scenario_type: string;
  status: string;
  model_name: string;
  model_version: string;
  input_data_version: string | null;
  parameters: Record<string, unknown>;
  assumptions: Record<string, unknown>;
  warnings: string[];
  results: SimResult[];
  created_at?: string;
}

// ---- Phase 8 types ----
export interface AgentRoster {
  agents: { agent: string; count: string; behaviour: string; calibrated_from: string }[];
  default_assumptions: Record<string, number>;
}
export interface Percentiles {
  p5: number;
  p50: number;
  p95: number;
  mean: number;
}
export interface AgentSimResult {
  policy: { price_change_percent: number; monthly_opex_delta: number };
  horizon_months: number;
  iterations: number;
  cumulative_net_profit: Percentiles;
  monthly_net_profit_path: { month: number; p5: number; p50: number; p95: number; mean: number }[];
  probability_of_cumulative_loss: number;
  expected_active_customers_end: number;
  customers_start: number;
  assumptions: Record<string, number>;
  calibration: Record<string, number>;
  provenance: { calibration: string; behaviour: string; outcome: string };
}
export interface AgentCompareResult {
  strategies: {
    name: string;
    price_change_percent: number;
    expected_cumulative_net_profit: number;
    p5: number;
    p95: number;
    probability_of_loss: number;
    expected_active_customers_end: number;
  }[];
  best_by_expected_profit: string | null;
  calibration: Record<string, number>;
}

// ---- Phase 7 types ----
export interface ImpactSimResult {
  metric: string;
  baseline: number;
  scenario: number;
  change_percent: number;
}
export interface ImpactAssessment {
  driver: string;
  title: string;
  fact: { label: string; value: number; unit: string; period: string; source: string; source_url: string };
  assumptions: Record<string, unknown>;
  possible_impact: Record<string, unknown>;
  lever: { field: string; value: number };
  simulation: { results: ImpactSimResult[]; net_profit_change_percent: number };
  risk: string;
  recommended_action: string;
  materiality: { net_profit_change_percent: number; material: boolean };
  provenance: { fact: string; mapping: string; numbers: string };
}
export interface ImpactScanResult {
  assessments: ImpactAssessment[];
  alerts_created: number;
  has_market_data: boolean;
  note: string;
}

// ---- Notification types ----
export interface ReorderItem {
  product_id: number;
  product_code: string;
  product_name: string;
  abc_class: string | null;
  recommended_order_quantity: number;
  estimated_order_cost: number | null;
  margin_at_risk_over_horizon: number | null;
  recommendation_status: string;
  warnings: string[];
}
export interface ReorderPlan {
  status: string;
  as_of: string;
  counts: { to_order_now: number; needs_review: number; insufficient_data: number };
  total_estimated_restock_cost: number;
  items: ReorderItem[];
}

export interface ReceivableDebtor {
  customer_id: number | null;
  customer_name: string;
  outstanding: number;
}
export interface ReceivablesSummary {
  as_of: string;
  total_outstanding: number;
  overdue_total: number;
  aging: Record<string, number>;
  open_invoice_count: number;
  debtors: ReceivableDebtor[];
}
export interface OverdueInvoice {
  invoice_id: number;
  invoice_number: string;
  customer_id: number | null;
  customer_name: string;
  balance: number;
  days_overdue: number;
  due: string;
}
export interface OverdueList {
  as_of: string;
  count: number;
  total: number;
  invoices: OverdueInvoice[];
}
export interface StatementEvent {
  date: string;
  type: string;
  ref: string;
  charge: number;
  payment: number;
  balance: number;
}
export interface CustomerStatement {
  customer_id: number;
  customer_name: string;
  credit_limit: number | null;
  outstanding: number;
  events: StatementEvent[];
}

export interface TaxSummary {
  period: { start: string; end: string };
  revenue: number;
  vat: { rate: number; output_vat: number; input_vat: number; vat_payable: number };
  income_tax: {
    cost_of_goods_sold: number;
    operating_expenses: number;
    taxable_profit: number;
    annualised_turnover: number;
    cit_rate: number;
    cit_band: string;
    income_tax: number;
  };
  total_estimated_tax: number;
  disclaimer: string;
}

export interface CashFlow {
  as_of: string;
  window_days: number;
  money_in: number;
  money_out: number;
  money_out_breakdown: { supplier_payments: number; expenses: number };
  net_cash_flow: number;
  owed_to_us: number;
  we_owe: number;
  net_position: number;
  note: string;
}
export interface PayablesSummary {
  total_payable: number;
  overdue_total: number;
  aging: Record<string, number>;
  open_purchase_count: number;
  creditors: { supplier_id: number | null; supplier_name: string; owed: number }[];
}

export interface AuditEvent {
  id: number;
  action: string;
  entity_type: string | null;
  entity_id: number | null;
  user_id: number | null;
  user_name: string | null;
  source: string;
  summary: string | null;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  at: string | null;
}
export interface AuditPage {
  items: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface NotificationItem {
  id: number;
  title: string;
  body: string | null;
  category: string;
  severity: string;
  link: string | null;
  is_read: boolean;
  created_at: string;
}

// ---- Users & admin types ----
export interface UserRow {
  id: number;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
}
export interface DataStats {
  tables: { table: string; total: number; demo: number; real: number }[];
  total_demo_rows: number;
  users: number;
}
export interface PurgeResult {
  deleted: Record<string, number>;
  total_deleted: number;
  message: string;
}

// ---- Shipping types ----
export interface ShippingStatus {
  enabled: boolean;
  connected: boolean;
  vessels_tracked: number;
  messages_received: number;
  nigeria_bound: number;
  by_region: Record<string, number>;
  by_origin: Record<string, number>;
  nigeria_watch: {
    china_declared: number;
    china_arrived: number;
    turkey_declared: number;
    turkey_arrived: number;
  };
  last_message_at: string | null;
  error: string | null;
}
export interface ProductHistoryEvent {
  kind: string; // STOCK | PRICE
  type: string; // RECEIVE | SALE | TRANSFER_* | ADJUST | PRICE_CHANGE
  at: string | null;
  quantity?: number;
  unit_cost?: number | null;
  warehouse?: string | null;
  customer?: string | null;
  invoice?: string | null;
  user?: string | null;
  note?: string | null;
  selling_price?: number | null;
  purchase_cost?: number | null;
}
export interface ProductHistory {
  product_id: number;
  counts: { stock_events: number; price_changes: number };
  events: ProductHistoryEvent[];
}

export interface SupplierTraceProduct {
  product_id: number;
  product_code: string | null;
  product_name: string | null;
  total_received: number;
  last_received: string | null;
}
export interface SupplierTraceShipment {
  lot_code: string | null;
  product: string | null;
  warehouse: string | null;
  received_date: string | null;
  quantity: number;
  unit_cost: number | null;
  shipment_ref: string | null;
  vessel_mmsi: string | null;
  purchase_id: number | null;
}
export interface SupplierTracePayment {
  amount: number;
  method: string | null;
  paid_at: string;
  reference: string | null;
  txid: string | null;
  from_account: string | null;
  from_name: string | null;
  to_account: string | null;
  to_name: string | null;
}
export interface SupplierTrace {
  status: string;
  supplier_id: number;
  supplier_code: string | null;
  supplier_name: string;
  location: string | null;
  currency: string | null;
  lead_time_days: number | null;
  reliability_score: number | null;
  products: SupplierTraceProduct[];
  warehouses: string[];
  shipments: SupplierTraceShipment[];
  we_owe: number;
  payments: SupplierTracePayment[];
  provenance: string;
}

export interface ProductImage {
  id: number;
  url: string;
  is_primary: boolean;
  sort_order: number;
}
export interface CompanyProfile {
  name: string;
  address: string | null;
  phone: string | null;
  email: string | null;
  tax_id: string | null;
  website: string | null;
  footer_note: string | null;
}
export interface InvoiceDetail {
  id: number;
  invoice_number: string;
  invoice_date: string;
  customer_id: number | null;
  customer_name: string | null;
  currency: string;
  subtotal: number;
  discount: number;
  tax: number;
  shipping: number;
  shipping_note: string | null;
  total: number;
  verification_status: string;
  created_by: string | null;
  updated_by: string | null;
  version_no: number;
  version_count: number;
  amount_paid?: number;
  payment_status?: string;
  balance?: number;
  payments?: InvoicePayment[];
  lines: {
    product_id: number | null;
    original_description: string | null;
    quantity: number;
    unit_price: number;
    line_total: number;
  }[];
}
export interface InvoicePayment {
  id: number;
  amount: number;
  method: string;
  reference: string | null;
  paid_at: string;
  status: string;
  note: string | null;
  recorded_by: string | null;
  recorded_at: string | null;
  txid: string | null;
  from_account: string | null;
  from_name: string | null;
  to_account: string | null;
  to_name: string | null;
}
export interface InvoiceVersionRow {
  version_no: number;
  snapshot: Record<string, unknown>;
  changed_by: string | null;
  change_note: string | null;
  changed_at: string | null;
}
export interface StockLot {
  id: number;
  lot_code: string;
  product_id: number;
  product: string | null;
  product_image: string | null;
  warehouse_id: number;
  warehouse: string | null;
  supplier: string | null;
  purchase_id: number | null;
  received_date: string | null;
  quantity_received: number;
  quantity_remaining: number;
  unit_cost: number | null;
  shipment_ref: string | null;
  vessel_mmsi: number | null;
  status: string;
  note: string | null;
}
export interface VesselSnapshot {
  mmsi: number;
  tracked: boolean;
  name?: string | null;
  region?: string | null;
  origin_region?: string | null;
  bound_for_nigeria?: boolean;
  arrived_nigeria?: boolean;
  last_seen?: string | null;
}
export interface StockMovement {
  id: number;
  type: string;
  quantity: number;
  occurred_at: string | null;
  warehouse: string | null;
  invoice_id: number | null;
  customer: string | null;
  counterparty_warehouse: string | null;
  unit_cost: number | null;
  note: string | null;
  version?: number;
  balance_after?: number;
}
export interface StockLotDetail extends StockLot {
  movements: StockMovement[];
  sold_to: string[];
  invoices: number[];
  vessel: VesselSnapshot | null;
}
export interface LaneSignal {
  lane: string;
  vessels_tracked: number;
  with_speed: number;
  moving: number;
  stationary: number;
  stationary_share: number | null;
  median_speed_kn: number | null;
}
export interface DisruptionItem {
  title: string;
  source: string;
  source_url: string | null;
  published: string;
  relevance: number | null;
  factors: string[];
}
export interface LaneConditions {
  lanes: LaneSignal[];
  disruptions: { natural: DisruptionItem[]; human: DisruptionItem[] };
  counts: { natural: number; human: number };
  note: string;
}
export interface Vessel {
  mmsi: number;
  name: string;
  lat: number | null;
  lon: number | null;
  sog: number | null;
  cog: number | null;
  ship_type: number | null;
  destination: string | null;
  eta: string | null;
  region: string;
  origin_region: string | null;
  bound_for_nigeria: boolean;
  arrived_nigeria: boolean;
  last_seen: string | null;
}

// ---- Phase 6 types ----
export interface MarketIndicator {
  indicator: string;
  label: string;
  value: number;
  unit: string;
  period: string;
  source: string;
  source_url: string;
  data_origin: string;
  implication: string | null;
}
export interface MarketNews {
  id: number;
  title: string;
  summary: string;
  source: string;
  source_url: string;
  published: string;
  relevance: number;
  data_origin: string;
}
export interface MarketSummary {
  indicators: MarketIndicator[];
  top_news: MarketNews[];
  has_data: boolean;
  note: string;
  provenance: string;
}
export interface MarketRefreshResult {
  provider: string;
  indicators_ingested: number;
  indicators_updated: number;
  news_ingested: number;
  sources: string[];
  as_of: string;
}

// ---- Phase 5 types ----
export interface DocumentItem {
  id: number;
  filename: string | null;
  content_type: string | null;
  status: string;
  ocr_confidence: number | null;
  created_at: string;
}
export interface Extraction {
  id: number;
  document_id: number;
  status: string;
  overall_confidence: number | null;
  extracted: {
    invoice_number?: string;
    invoice_date?: string;
    customer_name?: string;
    currency?: string;
    tax?: number;
    discount?: number;
    lines?: { description: string; quantity: number; unit_price: number; line_total: number }[];
  };
  matched: {
    customer?: { id: number | null; confidence: number; matched_text: string | null };
    lines?: { product_id: number | null; confidence: number; matched_text: string | null }[];
  };
  validation: { arithmetic_ok: boolean; issues: string[] };
  created_invoice_id: number | null;
  review_notes: string | null;
  created_at: string;
}

// ---- Phase 4 types ----
export interface AssistantToolCall {
  name: string;
  args: Record<string, unknown>;
  provenance: string;
  result: Record<string, unknown>;
}
export interface PurchaseLine {
  product_id: number | null;
  product_code: string | null;
  product_name: string | null;
  description: string | null;
  quantity: number;
  unit_cost: number;
  line_total: number;
}
export interface Purchase {
  id: number;
  reference: string;
  status: string; // REQUEST | ORDERED | RECEIVED | CANCELLED
  purchase_date: string | null;
  supplier_id: number | null;
  supplier_name: string | null;
  currency: string;
  subtotal: number;
  transport_cost: number;
  total: number;
  amount_paid: number;
  payment_status: string;
  line_count: number;
  lines?: PurchaseLine[];
}

export interface Waybill {
  id: number;
  waybill_number: string;
  invoice_id: number;
  status: string; // PENDING | DISPATCHED | DELIVERED | CANCELLED
  dispatched_at: string | null;
  apprentice_name: string | null;
  transport_company: string | null;
  driver_phone: string | null;
  vehicle_info: string | null;
  station: string | null;
  receiver_name: string | null;
  receiver_phone: string | null;
  destination: string | null;
  notes: string | null;
  created_at: string | null;
  created_by: string | null;
  invoice_number: string | null;
  invoice_total: number | null;
  customer_id: number | null;
  customer_name: string | null;
}

export interface AssistantProposal {
  action: string;
  confirmation_token: string;
  args?: Record<string, unknown> | null;
  message?: string;
}
export interface AssistantResponse {
  question: string;
  answer: string;
  provider: string;
  model: string | null;
  provenance: string;
  tool_calls: AssistantToolCall[];
  actions_taken: string[];
  proposals?: AssistantProposal[];
  disclaimer: string;
  conversation_id?: number;
  conversation_title?: string;
}
export interface ConversationSummary {
  id: number;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}
export interface ConversationMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  meta: {
    provider?: string;
    model?: string | null;
    provenance?: string;
    tool_calls?: AssistantToolCall[];
    actions_taken?: string[];
    disclaimer?: string;
  } | null;
  created_at: string;
}
export interface ConversationDetail {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ConversationMessage[];
}
export interface AssistantTool {
  name: string;
  description: string;
  provenance: string;
}

// ---- Phase 3 types ----
export interface TornadoRow {
  variable: string;
  low_input: number;
  high_input: number;
  low_value: number;
  high_value: number;
  swing: number;
}
export interface Tornado {
  target_metric: string;
  base_value: number;
  ranking: TornadoRow[];
}
export interface CompareScenario {
  name: string;
  values: Record<string, number>;
  deltas: Record<string, number>;
}
export interface Comparison {
  metrics: string[];
  baseline: Record<string, number>;
  scenarios: CompareScenario[];
  best_by_net_profit: string | null;
}

// ---- Phase 2 types ----
export interface CustomerMetric {
  customer_id: number;
  code: string;
  name: string;
  revenue: number;
  gross_profit: number;
  gross_margin: number;
  orders: number;
  avg_order_value: number;
  last_purchase: string | null;
  recency_days: number | null;
  avg_interval_days: number | null;
  churn_risk: boolean;
  churn_reason: string | null;
}
export interface CustomerIntel {
  summary: {
    customers_with_sales: number;
    total_revenue: number;
    at_risk_count: number;
    top1_revenue_share: number;
    top5_revenue_share: number;
  };
  top_by_profit: CustomerMetric[];
  at_risk: CustomerMetric[];
}
export interface ProductMetric {
  product_id: number;
  code: string;
  name: string;
  category: string | null;
  revenue: number;
  units: number;
  gross_profit: number;
  gross_margin: number;
  on_hand?: number;
}
export interface ProductIntel {
  summary: { products_sold: number; dead_stock_count: number };
  best_sellers: ProductMetric[];
  most_profitable: ProductMetric[];
  slow_movers: ProductMetric[];
  dead_stock: ProductMetric[];
}
export interface SupplierMetric {
  supplier_id: number;
  code: string;
  name: string;
  product_count: number;
  spend: number;
  lead_time_days: number | null;
  reliability_score: number | null;
}
export interface SupplierIntel {
  summary: { supplier_count: number; total_spend: number };
  suppliers: SupplierMetric[];
}
export interface FinancialRow {
  period: string;
  revenue: number;
  cogs: number;
  gross_profit: number;
  operating_expenses: number;
  net_profit: number;
  gross_margin: number;
  net_margin: number;
}
export interface DQIssue {
  category: string;
  severity: string;
  description: string;
  count: number;
  sample_ids: (number | string)[];
}
export interface DataQuality {
  score: number;
  grade: string;
  totals: { invoices: number; invoice_lines: number; products: number };
  issues: DQIssue[];
}
export interface ImportField {
  name: string;
  type: string;
  required: boolean;
}
export interface ImportPreview {
  columns: string[];
  sample_rows: Record<string, string>[];
  importable_entities: string[];
}
export interface ImportResult {
  import_id: number;
  entity_type: string;
  rows_total: number;
  rows_imported: number;
  rows_failed: number;
  errors: { row: number; error: string }[];
}
export interface ImportBatch {
  id: number;
  filename: string | null;
  status: string;
  rows_total: number | null;
  rows_imported: number | null;
  rows_failed: number | null;
  created_at: string;
}
