import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./index";
import type { IntakeVariant, JobView } from "./types";

export const qk = {
  job: (id: string) => ["job", id] as const,
  calls: (id: string) => ["calls", id] as const,
  report: (id: string) => ["report", id] as const,
  events: (id: string) => ["events", id] as const,
  vendorsDiscovery: () => ["vendorsDiscovery"] as const,
  vendorResearch: (id: string) => ["vendorResearch", id] as const,
};

export function useJob(jobId: string, { poll = false }: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: qk.job(jobId),
    queryFn: () => api.getJob(jobId),
    enabled: !!jobId,
    refetchInterval: poll ? 1500 : false,
  });
}

export function useStartCalls() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => api.startCalls(jobId),
    onSuccess: (data, jobId) => {
      qc.setQueryData(qk.calls(jobId), data);
      qc.invalidateQueries({ queryKey: qk.job(jobId) });
    },
  });
}

export function useNegotiate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => api.negotiateJob(jobId),
    onSuccess: (_data, jobId) => {
      qc.invalidateQueries({ queryKey: qk.job(jobId) });
      qc.invalidateQueries({ queryKey: qk.calls(jobId) });
      qc.invalidateQueries({ queryKey: qk.events(jobId) });
    },
  });
}

export function useVendorsDiscovery(enabled = false) {
  return useQuery({
    queryKey: qk.vendorsDiscovery(),
    queryFn: () => api.getVendorsDiscovery(),
    enabled,
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function useVendorResearch(jobId: string, enabled = true) {
  return useQuery({
    queryKey: qk.vendorResearch(jobId),
    queryFn: () => api.getVendorResearch(jobId),
    enabled: enabled && !!jobId,
    retry: false,
  });
}

function useVendorResearchMutation<TVariables>(
  mutationFn: (variables: TVariables) => ReturnType<typeof api.getVendorResearch>,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: (data, variables) => {
      const jobId =
        typeof variables === "string" ? variables : (variables as { jobId: string }).jobId;
      qc.setQueryData(qk.vendorResearch(jobId), data);
    },
  });
}

export function useDiscoverJobVendors() {
  return useVendorResearchMutation(
    ({ jobId, refresh = false }: { jobId: string; refresh?: boolean }) =>
      api.discoverJobVendors(jobId, refresh),
  );
}

export function useSaveVendorShortlist() {
  return useVendorResearchMutation(({ jobId, vendorIds }: { jobId: string; vendorIds: string[] }) =>
    api.saveVendorShortlist(jobId, { vendor_ids: vendorIds }),
  );
}

export function useClearVendorShortlist() {
  return useVendorResearchMutation((jobId: string) => api.clearVendorShortlist(jobId));
}

export function useAnalyzeVendorWebsites() {
  return useVendorResearchMutation(
    ({ jobId, refresh = false }: { jobId: string; refresh?: boolean }) =>
      api.analyzeVendorWebsites(jobId, refresh),
  );
}

export function useExtractVendorContacts() {
  return useVendorResearchMutation((jobId: string) => api.extractVendorContacts(jobId));
}

export function useSaveVendorCallAuthorizations() {
  return useVendorResearchMutation(
    ({
      jobId,
      request,
    }: {
      jobId: string;
      request: Parameters<typeof api.saveVendorCallAuthorizations>[1];
    }) => api.saveVendorCallAuthorizations(jobId, request),
  );
}

export function useClearVendorCallAuthorizations() {
  return useVendorResearchMutation((jobId: string) => api.clearVendorCallAuthorizations(jobId));
}

export function useCalls(jobId: string, { poll = false }: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: qk.calls(jobId),
    queryFn: () => api.getCalls(jobId),
    enabled: !!jobId,
    refetchInterval: poll ? 1500 : false,
  });
}

export function useReport(jobId: string) {
  return useQuery({
    queryKey: qk.report(jobId),
    queryFn: () => api.getReport(jobId),
    enabled: !!jobId,
    retry: false,
  });
}

export function useEvents(jobId: string, { poll = false }: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: qk.events(jobId),
    queryFn: () => api.getEvents(jobId),
    enabled: !!jobId,
    refetchInterval: poll ? 2000 : false,
  });
}

export function useConfirmJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => api.confirmJob(jobId),
    onSuccess: (data) => {
      qc.setQueryData(qk.job(data.id), data);
    },
  });
}

export function useUpdateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ jobId, patch }: { jobId: string; patch: Partial<JobView> }) =>
      api.updateJob(jobId, patch),
    onSuccess: (data) => {
      qc.setQueryData(qk.job(data.id), data);
    },
  });
}

export function useCreateJobFromDocument() {
  return useMutation({
    mutationFn: ({ file, variant }: { file: File; variant?: IntakeVariant }) =>
      api.createJobFromDocument(file, variant),
  });
}

// Voice intake in live mode is not connected — no /api/intake/voice route
// exists on the backend. Demo mode still simulates it via the demo adapter,
// which we call directly to avoid pretending a live endpoint exists.
import * as demo from "./demo/adapter";
export function useCreateJobFromVoice() {
  return useMutation({
    mutationFn: (variant?: IntakeVariant) => demo.createJobFromVoice(variant),
  });
}
