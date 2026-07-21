import { useEffect, useSyncExternalStore } from "react";
import type { components, paths } from "./schema";

type Schemas = components["schemas"];

export type JobSpecV1 = Schemas["JobSpecV1"];
export type JobRecord = Schemas["JobRecord"];
export type CallRecord = Schemas["CallRecord"];
export type QuoteV1 = Schemas["QuoteV1"];
export type RecommendationV1 = Schemas["RecommendationV1"];
export type JobEventsResponse = Schemas["JobEventsResponse"];
export type VendorDiscoveryResponse = Schemas["VendorDiscoveryResponse"];
export type HealthResponse = Schemas["HealthResponse"] | Schemas["RuntimeHealthResponse"];
export type IntakeSessionResponse = Schemas["IntakeSessionResponse"];
export type BrowserVoiceTokenResponse = Schemas["BrowserVoiceTokenResponse"];
export type AttachIntakeConversationRequest = Schemas["AttachIntakeConversationRequest"];
export type IntegrationStatusSnapshot = Schemas["IntegrationStatusSnapshot"];
export type JobVendorResearchV1 = Schemas["JobVendorResearchV1"];
export type VendorShortlistRequest = Schemas["VendorShortlistRequest"];
export type RuntimeMode = "demo" | "live";
export type FieldErrors = Record<string, string>;
export type ApiErrorKind = "http" | "network" | "aborted" | "malformed";

const env = (typeof import.meta !== "undefined" ? import.meta.env : undefined) as
  Record<string, string | undefined> | undefined;

export const API_BASE_URL = (
  env?.VITE_API_BASE_URL || "https://veramove-api-demo-zukhriddingit.onrender.com"
).replace(/\/$/, "");

const SESSION_STORAGE_KEY = "veramove.runtimeMode.session";
const LEGACY_STORAGE_KEY = "veramove.runtimeMode";

function readSessionMode(): RuntimeMode | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    return value === "demo" || value === "live" ? value : null;
  } catch {
    return null;
  }
}

function removeLegacyStoredMode(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    // Storage can be unavailable; the Live production default stays active.
  }
}

function readEnvMode(): RuntimeMode {
  return (env?.VITE_DEMO_MODE ?? "").toLowerCase() === "true" ? "demo" : "live";
}

const listeners = new Set<() => void>();
let currentMode = readEnvMode();

function publishMode(next: RuntimeMode): void {
  if (next === currentMode) return;
  currentMode = next;
  listeners.forEach((callback) => callback());
}

export function getRuntimeMode(): RuntimeMode {
  return currentMode;
}

export function hydrateRuntimeMode(): void {
  removeLegacyStoredMode();
  const storedMode = readSessionMode();
  if (storedMode) publishMode(storedMode);
}

export function useRuntimeMode(): RuntimeMode {
  const mode = useSyncExternalStore(
    (callback) => {
      listeners.add(callback);
      return () => listeners.delete(callback);
    },
    getRuntimeMode,
    readEnvMode,
  );

  useEffect(() => {
    hydrateRuntimeMode();
  }, []);

  return mode;
}

export function setRuntimeMode(next: RuntimeMode, options?: { redirectTo?: string }): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, next);
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    // Storage can be unavailable in privacy modes; navigation still works.
  }
  publishMode(next);
  if (options?.redirectTo) window.location.assign(options.redirectTo);
  else window.location.reload();
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number;
  readonly detail: string;
  readonly fieldErrors?: FieldErrors;
  readonly body?: unknown;

  constructor(init: {
    kind: ApiErrorKind;
    status: number;
    detail: string;
    fieldErrors?: FieldErrors;
    body?: unknown;
  }) {
    super(init.detail);
    this.name = "ApiError";
    this.kind = init.kind;
    this.status = init.status;
    this.detail = init.detail;
    this.fieldErrors = init.fieldErrors;
    this.body = init.body;
  }
}

interface FastApiValidationItem {
  loc?: unknown[];
  msg?: string;
}

function collectFieldErrors(items: unknown): FieldErrors | undefined {
  if (!Array.isArray(items)) return undefined;
  const fieldErrors: FieldErrors = {};
  for (const item of items as FastApiValidationItem[]) {
    const path = Array.isArray(item?.loc) ? item.loc.map(String).join(".") : "";
    if (path) fieldErrors[path] = item.msg || "Invalid value";
  }
  return Object.keys(fieldErrors).length ? fieldErrors : undefined;
}

function normalizeError(status: number, statusText: string, body: unknown) {
  if (body && typeof body === "object" && "error" in body) {
    const error = (body as { error?: unknown }).error;
    if (error && typeof error === "object" && "message" in error) {
      const message = (error as { message?: unknown }).message;
      if (typeof message === "string" && message.trim()) return { detail: message };
    }
  }
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return { detail };
    if (Array.isArray(detail)) {
      const fieldErrors = collectFieldErrors(detail);
      return {
        detail: fieldErrors ? Object.values(fieldErrors)[0] : "Some fields need attention.",
        fieldErrors,
      };
    }
  }
  return { detail: statusText || `Request failed with status ${status}` };
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = path.startsWith("http") ? path : `${API_BASE_URL}${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body && !(init.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...(init.headers ?? {}),
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError({ kind: "aborted", status: 0, detail: "Request was cancelled." });
    }
    throw new ApiError({
      kind: "network",
      status: 0,
      detail: "Couldn't reach the backend. Check your connection and try again.",
    });
  }

  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = undefined;
    }
    const normalized = normalizeError(response.status, response.statusText, body);
    throw new ApiError({
      kind: "http",
      status: response.status,
      detail: normalized.detail,
      fieldErrors: normalized.fieldErrors,
      body,
    });
  }

  if (response.status === 204) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError({
      kind: "malformed",
      status: response.status,
      detail: "The backend returned a response we couldn't read.",
    });
  }
}

export const apiClient = {
  health: () => apiFetch<HealthResponse>("/health"),
  integrationStatus: () => apiFetch<IntegrationStatusSnapshot>("/api/integrations/status"),
  createIntakeSession: () =>
    apiFetch<IntakeSessionResponse>("/api/intake/sessions", { method: "POST" }),
  issueBrowserVoiceToken: (sessionId: string) =>
    apiFetch<BrowserVoiceTokenResponse>(`/api/intake/sessions/${sessionId}/voice-token`, {
      method: "POST",
    }),
  attachIntakeConversation: (sessionId: string, conversationId: string) =>
    apiFetch<IntakeSessionResponse>(`/api/intake/sessions/${sessionId}/conversation`, {
      method: "POST",
      body: JSON.stringify({ conversation_id: conversationId }),
    }),
  getIntakeSession: (sessionId: string) =>
    apiFetch<IntakeSessionResponse>(`/api/intake/sessions/${sessionId}`),
  createJob: (jobSpec: JobSpecV1) =>
    apiFetch<JobRecord>("/api/jobs", { method: "POST", body: JSON.stringify(jobSpec) }),
  createJobFromDocument: (documentText: string) =>
    apiFetch<JobRecord>("/api/intake/document", {
      method: "POST",
      body: JSON.stringify({ document_text: documentText }),
    }),
  getJob: (jobId: string) => apiFetch<JobRecord>(`/api/jobs/${jobId}`),
  replaceJobSpec: (jobId: string, jobSpec: JobSpecV1) =>
    apiFetch<JobRecord>(`/api/jobs/${jobId}`, {
      method: "PUT",
      body: JSON.stringify(jobSpec),
    }),
  confirmJob: (jobId: string) =>
    apiFetch<JobRecord>(`/api/jobs/${jobId}/confirm`, { method: "POST" }),
  startCalls: (jobId: string) =>
    apiFetch<JobRecord>(`/api/jobs/${jobId}/calls`, { method: "POST" }),
  negotiate: (jobId: string) =>
    apiFetch<JobRecord>(`/api/jobs/${jobId}/negotiate`, { method: "POST" }),
  getReport: (jobId: string) => apiFetch<RecommendationV1>(`/api/jobs/${jobId}/report`),
  getEvents: (jobId: string) => apiFetch<JobEventsResponse>(`/api/jobs/${jobId}/events`),
  discoverVendors: () => apiFetch<VendorDiscoveryResponse>("/api/vendors/discover"),
  getVendorResearch: (jobId: string) =>
    apiFetch<JobVendorResearchV1>(`/api/jobs/${jobId}/vendor-research`),
  discoverJobVendors: (jobId: string, refresh = false) =>
    apiFetch<JobVendorResearchV1>(
      `/api/jobs/${jobId}/vendor-research/discover${refresh ? "?refresh=true" : ""}`,
      { method: "POST" },
    ),
  saveVendorShortlist: (jobId: string, request: VendorShortlistRequest) =>
    apiFetch<JobVendorResearchV1>(`/api/jobs/${jobId}/vendor-research/shortlist`, {
      method: "PUT",
      body: JSON.stringify(request),
    }),
  clearVendorShortlist: (jobId: string) =>
    apiFetch<JobVendorResearchV1>(`/api/jobs/${jobId}/vendor-research/shortlist`, {
      method: "DELETE",
    }),
  analyzeVendorWebsites: (jobId: string, refresh = false) =>
    apiFetch<JobVendorResearchV1>(
      `/api/jobs/${jobId}/vendor-research/analyze${refresh ? "?refresh=true" : ""}`,
      { method: "POST" },
    ),
};

export type { components as OpenAPIComponents, paths as OpenAPIPaths } from "./schema";
export type ApiPaths = paths;
