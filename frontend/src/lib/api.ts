/** API client for Compendium backend. */

const BASE = "";

function encodePath(path: string): string {
  return path
    .replace(/^\/+/, "")
    .split("/")
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await res.json().catch(() => null) : await res.text();

  if (!res.ok) {
    const message =
      payload &&
      typeof payload === "object" &&
      "error" in payload &&
      typeof payload.error === "string"
        ? payload.error
        : `${res.status} ${res.statusText}`;
    throw new Error(message);
  }

  return payload as T;
}

function get<T>(path: string): Promise<T> {
  return request<T>(path);
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function postForm<T>(path: string, formData: FormData): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: formData,
  });
}

export interface Health {
  status: string;
  version: string;
  project: string;
}

export interface Status {
  project_name: string;
  raw_source_count: number;
  wiki_article_count: number;
  default_provider: string;
}

export interface UsageSummary {
  month: string;
  total_tokens: number;
  estimated_cost: number;
}

export interface UsagePayload {
  summary: UsageSummary;
  breakdown: Record<string, { tokens: number; estimated_cost: number }>;
}

export interface ItemPath {
  name: string;
  path: string;
}

export interface ArticleContent {
  path: string;
  content: string;
}

export interface SearchResult {
  path: string;
  title: string;
  category: string;
  score: number;
  snippet: string;
}

export interface SearchPayload {
  query: string;
  results: SearchResult[];
}

export interface FilingResult {
  status: string;
  message?: string;
  existing?: string;
  similar_path?: string;
  filed_path?: string;
  category?: string;
  backlinks_added?: number;
  action?: string;
}

export interface AskRequest {
  question: string;
  sessionId?: string;
  output?: "text" | "report" | "slides" | "html" | "chart" | "canvas";
  file?: boolean;
  resolution?: "merge" | "replace" | "keep_both" | "cancel";
  count?: number;
}

export interface AskResult {
  answer: string;
  sources_used: string[];
  tokens_used: number;
  articles_loaded: number;
  output: string;
  output_path?: string;
  extra_paths?: string[];
  filing?: FilingResult;
}

export interface UploadResult {
  source_path: string;
  output_path: string | null;
  success: boolean;
  message: string;
  duplicate_of: string | null;
  ocr_confidence: number | null;
}

export interface UploadResponse {
  total: number;
  succeeded: number;
  failed: number;
  duplicate_mode: string;
  results: UploadResult[];
}

export interface LintIssue {
  severity: string;
  category: string;
  location: string;
  description: string;
  suggestion: string;
}

export interface LintResult {
  total: number;
  critical: number;
  warning: number;
  info: number;
  reason: string;
  issues: LintIssue[];
}

export interface ModelDraft {
  provider: string;
  model: string;
  endpoint?: string | null;
}

export interface PricingInfo {
  input_per_million: number;
  output_per_million: number;
}

export interface OperationModelDetails extends ModelDraft {
  saved: boolean;
  context_window: number | null;
  pricing: PricingInfo | null;
  error: string | null;
}

export interface SettingsPayload {
  status?: string;
  changed?: string[];
  models: {
    default_provider: string;
    compilation: ModelDraft;
    qa: ModelDraft;
    lint: ModelDraft;
  };
  templates: {
    default: string;
    domain: string;
  };
  lint: {
    schedule: "manual" | "daily" | "weekly";
    missing_data_web_search: boolean;
  };
  providers: Record<string, { saved: boolean }>;
  operations: {
    default_provider: string;
    compilation: OperationModelDetails;
    qa: OperationModelDetails;
    lint: OperationModelDetails;
  };
}

export interface ProviderTestResult {
  ok: boolean;
  provider?: string;
  model?: string;
  context_window?: number;
  pricing?: PricingInfo | null;
  error?: string;
}

export interface SessionSource {
  id: string;
  title: string;
  word_count: string;
  path: string;
}

export interface SessionSummary {
  session_id: string;
  kind: "compile" | "update";
  mode: "interactive" | "batch";
  status: "running" | "awaiting_approval" | "completed" | "cancelled" | "failed";
  created_at: string;
  updated_at: string;
  branch: string | null;
  source_count: number;
  current_index: number;
  sources: SessionSource[];
  pending_source: SessionSource | null;
  pending_summary: Record<string, unknown> | null;
  approved_summaries: Record<string, unknown>[];
  result: Record<string, unknown> | null;
  error: string | null;
  audit_log_path: string | null;
}

export interface GraphNode {
  id: string;
  name: string;
  category: string;
  links: number;
  path: string;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
  node_count: number;
  edge_count: number;
}

export const api = {
  health: () => get<Health>("/api/health"),
  status: () => get<Status>("/api/status"),
  usage: () => get<UsagePayload>("/api/usage"),
  sources: () => get<ItemPath[]>("/api/sources"),
  articles: () => get<ItemPath[]>("/api/articles"),
  article: (path: string) => get<ArticleContent>(`/api/article/${encodePath(path)}`),
  search: (query: string, limit = 10) =>
    get<SearchPayload>(`/api/search?q=${encodeURIComponent(query)}&limit=${limit}`),
  ask: (requestBody: AskRequest) =>
    post<AskResult>("/api/ask", {
      question: requestBody.question,
      session_id: requestBody.sessionId ?? "web-default",
      output: requestBody.output ?? "text",
      file: requestBody.file ?? false,
      resolution: requestBody.resolution,
      count: requestBody.count,
    }),
  outputRender: (query: string, answer: string, sourcesUsed: string[], output: string) =>
    post<{ output: string; output_path: string; extra_paths: string[] }>("/api/output-render", {
      query,
      answer,
      sources_used: sourcesUsed,
      output,
    }),
  fileToWiki: (path: string, resolution?: string) =>
    post<FilingResult>("/api/file-to-wiki", { path, resolution }),
  upload: (files: File[], duplicateMode: string) => {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
    }
    form.append("duplicate_mode", duplicateMode);
    return postForm<UploadResponse>("/api/ingest/upload", form);
  },
  lint: () => get<LintResult>("/api/lint"),
  settings: () => get<SettingsPayload>("/api/settings"),
  saveSettings: (payload: {
    compilation: ModelDraft;
    qa: ModelDraft;
    lint_model: ModelDraft;
    templates: SettingsPayload["templates"];
    lint_settings: SettingsPayload["lint"];
    default_provider: string;
  }) => post<SettingsPayload>("/api/settings/model-assignments", payload),
  testProvider: (payload: ModelDraft) =>
    post<ProviderTestResult>("/api/settings/test-provider", payload),
  saveProviderKey: (provider: string, key: string) =>
    post<{ status: string }>("/api/settings/key", { provider, key }),
  deleteProviderKey: (provider: string) =>
    post<{ status: string }>("/api/settings/key", { provider, key: "" }),
  startCompileSession: (payload: { mode: "interactive" | "batch"; branch?: string }) =>
    post<SessionSummary>("/api/compile/session", payload),
  getCompileSession: (sessionId: string) =>
    get<SessionSummary>(`/api/compile/session/${encodeURIComponent(sessionId)}`),
  approveCompileSession: (
    sessionId: string,
    payload: { approve: boolean; summary_override?: Record<string, unknown> },
  ) =>
    post<SessionSummary>(
      `/api/compile/session/${encodeURIComponent(sessionId)}/approve`,
      payload,
    ),
  startUpdateSession: (payload: { paths?: string[]; branch?: string }) =>
    post<SessionSummary>("/api/update/session", payload),
  getUpdateSession: (sessionId: string) =>
    get<SessionSummary>(`/api/update/session/${encodeURIComponent(sessionId)}`),
  graph: () => get<GraphPayload>("/api/graph"),
  downloadUrl: (path: string) => `${BASE}/api/download/${encodePath(path)}`,
};
