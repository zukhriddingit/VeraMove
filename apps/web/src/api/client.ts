import type { components } from "./schema";

export type HealthResponse = components["schemas"]["HealthResponse"];
export type JobSpecV1 = components["schemas"]["JobSpecV1"];
export type JobRecord = components["schemas"]["JobRecord"];
export type RecommendationV1 = components["schemas"]["RecommendationV1"];

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

type ApiErrorBody = {
  detail?: string;
  error?: { message?: string };
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null;
    throw new Error(body?.error?.message ?? body?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  createJob: (jobSpec: JobSpecV1) =>
    request<JobRecord>("/api/jobs", { method: "POST", body: JSON.stringify(jobSpec) }),
  getJob: (jobId: string) => request<JobRecord>(`/api/jobs/${jobId}`),
  confirmJob: (jobId: string) => request<JobRecord>(`/api/jobs/${jobId}/confirm`, { method: "POST" }),
  startCalls: (jobId: string) => request<JobRecord>(`/api/jobs/${jobId}/calls`, { method: "POST" }),
  negotiate: (jobId: string) => request<JobRecord>(`/api/jobs/${jobId}/negotiate`, { method: "POST" }),
  getReport: (jobId: string) => request<RecommendationV1>(`/api/jobs/${jobId}/report`),
};
