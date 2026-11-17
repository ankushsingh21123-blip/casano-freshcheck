export interface EvidenceItem {
  title: string;
  url: string;
  date: string | null;
  date_display: string;
  date_source: string;
  snippet: string;
  score: number | null;
}

export interface CheckRecord {
  id: number;
  question: string;
  answer: string;
  answer_date: string | null;
  topic: string;
  mode: string;
  verdict: string;
  query: string;
  reasons: string[];
  signals: Record<string, unknown>;
  evidence: EvidenceItem[];
  error: { kind: string; detail: string } | null;
  message: string;
  created_at: string;
}

export interface Health {
  status: string;
  mode: string;
  service: string;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(
      `Request failed (${response.status}): ${text.slice(0, 300)}`
    );
  }
  return (await response.json()) as T;
}

export function getHealth(): Promise<Health> {
  return request<Health>("/health");
}

export function createCheck(payload: {
  question: string;
  answer: string;
  answer_date?: string;
  topic: string;
}): Promise<CheckRecord> {
  return request<CheckRecord>("/checks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listChecks(): Promise<CheckRecord[]> {
  const body = await request<{ checks: CheckRecord[] }>("/checks");
  return body.checks;
}

export function getCheck(id: number): Promise<CheckRecord> {
  return request<CheckRecord>(`/checks/${id}`);
}
