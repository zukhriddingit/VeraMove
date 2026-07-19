import { apiClient } from "@/api/client";
import { toCallView, toJobEventView, toJobView, toReportView, toVendorViews } from "./adapters";
import type { IntakeVariant, JobView, NegotiationView } from "./types";

export const getHealth = apiClient.health;
export const getIntegrationStatus = apiClient.integrationStatus;
export const createIntakeSession = apiClient.createIntakeSession;
export const issueBrowserVoiceToken = apiClient.issueBrowserVoiceToken;
export const attachIntakeConversation = apiClient.attachIntakeConversation;
export const getIntakeSession = apiClient.getIntakeSession;

export async function getJob(jobId: string) {
  return toJobView(await apiClient.getJob(jobId));
}

export async function confirmJob(jobId: string) {
  return toJobView(await apiClient.confirmJob(jobId));
}

// The canonical API intentionally has no draft PATCH route. Demo mode can
// persist local edits; live mode retains the imported review UI but confirms
// the JobSpec already held by the backend.
export async function updateJob(jobId: string, patch: Partial<JobView>): Promise<JobView> {
  const current = await getJob(jobId);
  return { ...current, ...patch };
}

export async function getCalls(jobId: string) {
  const record = await apiClient.getJob(jobId);
  return (record.calls ?? []).map(toCallView);
}

export async function startCalls(jobId: string) {
  const record = await apiClient.startCalls(jobId);
  return (record.calls ?? []).map(toCallView);
}

export async function getReport(jobId: string) {
  const [recommendation, record] = await Promise.all([
    apiClient.getReport(jobId),
    apiClient.getJob(jobId),
  ]);
  return toReportView(recommendation, record);
}

export async function getEvents(jobId: string) {
  const response = await apiClient.getEvents(jobId);
  return response.events.map(toJobEventView);
}

export async function getVendorsDiscovery() {
  return toVendorViews(await apiClient.discoverVendors());
}

export async function negotiateJob(jobId: string): Promise<NegotiationView> {
  const record = await apiClient.negotiate(jobId);
  return (
    (record.calls ?? []).map(toCallView).find((call) => call.negotiation)?.negotiation ?? {
      beforeTotal: 0,
      afterTotal: 0,
      delta: 0,
      leverageVendorId: "",
      addedInclusions: [],
    }
  );
}

export async function createJobFromDocumentText(
  text: string,
  _variant?: IntakeVariant,
): Promise<{ jobId: string }> {
  const record = await apiClient.createJobFromDocument(text);
  return { jobId: record.job_spec.job_id ?? "" };
}

export async function createJobFromDocument(
  file: File,
  variant?: IntakeVariant,
): Promise<{ jobId: string }> {
  return createJobFromDocumentText(await file.text(), variant);
}
