// Minimal typed API client. Token is held in localStorage (Phase 1 dev auth).
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const V1 = `${BASE}/api/v1`;

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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${V1}${path}`, { ...init, headers });
  if (!res.ok) {
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

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; role: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<{ id: number; email: string; full_name: string; role: string }>("/auth/me"),
  dashboardSummary: () => request<DashboardSummary>("/dashboard/summary"),
  revenueSeries: () =>
    request<{ series: { period: string; revenue: number }[] }>("/dashboard/revenue-timeseries"),
  alerts: () => request<{ items: AlertItem[] }>("/dashboard/alerts"),
  list: <T>(resource: string, params = "") =>
    request<{ items: T[]; total: number; limit: number; offset: number }>(
      `/${resource}${params}`,
    ),
  scenarioTypes: () => request<{ implemented: string[] }>("/simulations/scenario-types"),
  createSimulation: (body: unknown) =>
    request<Simulation>("/simulations", { method: "POST", body: JSON.stringify(body) }),
  runSimulation: (id: number) =>
    request<Simulation>(`/simulations/${id}/run`, { method: "POST" }),
  listSimulations: () => request<{ items: Simulation[]; total: number }>("/simulations"),

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
  assistantAsk: (question: string) =>
    request<AssistantResponse>("/assistant/ask", {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
  assistantTools: () => request<{ tools: AssistantTool[] }>("/assistant/tools"),

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
export interface AssistantResponse {
  question: string;
  answer: string;
  provider: string;
  model: string | null;
  provenance: string;
  tool_calls: AssistantToolCall[];
  actions_taken: string[];
  disclaimer: string;
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
