/** API client for Compendium backend */

const BASE = "";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// -- Endpoints --

export interface Status {
  project_name: string;
  raw_source_count: number;
  wiki_article_count: number;
  default_provider: string;
}

export interface Article {
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

export interface AskResult {
  answer: string;
  sources_used: string[];
  tokens_used: number;
  articles_loaded: number;
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
  issues: LintIssue[];
}

export const api = {
  health: () => get<{ status: string; version: string }>("/api/health"),
  status: () => get<Status>("/api/status"),
  sources: () => get<Article[]>("/api/sources"),
  articles: () => get<Article[]>("/api/articles"),
  article: (path: string) => get<ArticleContent>(`/api/article/${path}`),
  search: (q: string, limit = 10) =>
    get<{ query: string; results: SearchResult[] }>(
      `/api/search?q=${encodeURIComponent(q)}&limit=${limit}`
    ),
  ask: (question: string, sessionId = "web-default") =>
    post<AskResult>("/api/ask", { question, session_id: sessionId }),
  lint: () => get<LintResult>("/api/lint"),
  fileToWiki: (path: string) => post<Record<string, string>>("/api/file-to-wiki", { path }),
  graph: () =>
    get<{
      nodes: { id: string; name: string; category: string; links: number }[];
      edges: { source: string; target: string }[];
      node_count: number;
      edge_count: number;
    }>("/api/graph"),
};
