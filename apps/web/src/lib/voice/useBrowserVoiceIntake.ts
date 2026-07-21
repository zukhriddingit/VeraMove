import { useCallback, useEffect, useRef, useState } from "react";
import { useConversation } from "@elevenlabs/react";
import type { IntakeDataMode, IntakeSessionResponse, JobSpecV1 } from "@/api/client";
import {
  attachIntakeConversation,
  createIntakeSession,
  finishIntakeManually,
  getIntegrationStatus,
  getIntakeSession,
  issueBrowserVoiceToken,
  recoverIntakeSession,
  resumeIntakeSession,
} from "@/lib/api/endpoints";
import { nextVoicePhase, pollDecision, type BrowserVoicePhase } from "./browserVoiceState";

export type { BrowserVoicePhase } from "./browserVoiceState";

export interface VoiceTurn {
  id: string;
  role: "agent" | "user";
  text: string;
}

const POLL_INTERVAL_MS = 1_500;

function publicError(error: unknown): string {
  if (error instanceof DOMException && error.name === "NotAllowedError") {
    return "Microphone access was blocked. Allow microphone access and try again.";
  }
  if (error instanceof DOMException && error.name === "NotFoundError") {
    return "No microphone was found. Connect one and try again.";
  }
  return "The live voice interview could not start. Please try again or switch to Demo Mode.";
}

export function useBrowserVoiceIntake() {
  const [phase, setPhase] = useState<BrowserVoicePhase>("ready");
  const [dataMode, setDataMode] = useState<IntakeDataMode | null>(null);
  const [turns, setTurns] = useState<VoiceTurn[]>([]);
  const [jobSpec, setJobSpec] = useState<JobSpecV1 | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [missingFields, setMissingFields] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isActionPending, setIsActionPending] = useState(false);
  const sessionIdRef = useRef<string | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const pollingRef = useRef(false);
  const failedRef = useRef(false);
  const connectedRef = useRef(false);
  const mountedRef = useRef(true);
  const seenTurnsRef = useRef(new Set<string>());
  const endSessionRef = useRef<() => void>(() => undefined);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    pollingRef.current = false;
  }, []);

  const fail = useCallback(
    (message: string) => {
      failedRef.current = true;
      stopPolling();
      if (!mountedRef.current) return;
      setError(message);
      setPhase("failed");
    },
    [stopPolling],
  );

  const applySession = useCallback(
    (session: IntakeSessionResponse): boolean => {
      const next = nextVoicePhase(session);
      if (!next) return false;
      stopPolling();
      if (!mountedRef.current) return true;

      if (next === "completed" && session.job_spec) {
        setJobSpec(session.job_spec);
        setJobId(session.job_id);
        setMissingFields([]);
        setError(null);
        setPhase("completed");
        return true;
      }
      if (next === "incomplete" && session.partial_job_spec) {
        setJobSpec(session.partial_job_spec);
        setJobId(session.job_id);
        setMissingFields(session.missing_fields);
        setError(null);
        setPhase("incomplete");
        return true;
      }
      fail("The interview ended, but no safe move draft could be recovered. Please start over.");
      return true;
    },
    [fail, stopPolling],
  );

  const pollForResult = useCallback(
    async (completedAttempts = 0) => {
      const sessionId = sessionIdRef.current;
      if (!sessionId || failedRef.current || !mountedRef.current) return;
      pollingRef.current = true;

      let session: IntakeSessionResponse | null = null;
      try {
        session = await getIntakeSession(sessionId);
        if (!mountedRef.current || failedRef.current) return;
        if (applySession(session)) return;
      } catch {
        // Count a transient Render/network failure, then use the bounded provider repair below.
      }

      const attempts = completedAttempts + 1;
      const decision = pollDecision(attempts, session?.status ?? "in_progress");
      if (decision.kind === "poll") {
        pollTimerRef.current = window.setTimeout(
          () => void pollForResult(attempts),
          POLL_INTERVAL_MS,
        );
        return;
      }
      if (decision.kind === "recover") {
        try {
          const recovered = await recoverIntakeSession(sessionId);
          if (!mountedRef.current || failedRef.current) return;
          if (applySession(recovered)) return;
        } catch {
          // A still-processing provider result becomes an explicit retryable state.
        }
      }

      pollingRef.current = false;
      if (!mountedRef.current) return;
      setError(
        "The provider has not produced a final result yet. Retry once, or start over without waiting.",
      );
      setPhase("unavailable");
    },
    [applySession],
  );

  const beginFinalizing = useCallback(() => {
    if (pollingRef.current || failedRef.current || !sessionIdRef.current) return;
    setPhase("finalizing");
    void pollForResult();
  }, [pollForResult]);

  const { startSession, endSession, mode } = useConversation({
    onConnect: ({ conversationId }) => {
      const sessionId = sessionIdRef.current;
      if (!sessionId || !mountedRef.current) return;
      connectedRef.current = true;
      setPhase("connected");
      void attachIntakeConversation(sessionId, conversationId).catch(() => {
        endSessionRef.current();
        fail("The voice interview connected but could not be securely linked. Please start over.");
      });
    },
    onMessage: ({ event_id: eventId, message, role }) => {
      const text = message.trim();
      if (!text || !mountedRef.current) return;
      const key = `${eventId ?? "none"}:${role}:${text}`;
      if (seenTurnsRef.current.has(key)) return;
      seenTurnsRef.current.add(key);
      setTurns((current) => [...current, { id: key, role, text }]);
    },
    onError: () => {
      if (connectedRef.current && sessionIdRef.current) {
        beginFinalizing();
        return;
      }
      fail("The voice connection could not be established. Please try again.");
    },
    onDisconnect: () => {
      if (!mountedRef.current || failedRef.current) return;
      beginFinalizing();
    },
  });

  useEffect(() => {
    endSessionRef.current = endSession;
  }, [endSession]);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
      stopPolling();
      endSessionRef.current();
    };
  }, [stopPolling]);

  const connect = useCallback(
    async (session: IntakeSessionResponse) => {
      sessionIdRef.current = session.intake_session_id;
      setDataMode(session.data_mode);
      if (session.partial_job_spec) {
        setJobSpec(session.partial_job_spec);
        setMissingFields(session.missing_fields);
      }
      setPhase("connecting");
      const credential = await issueBrowserVoiceToken(session.intake_session_id);
      await startSession({
        conversationToken: credential.conversation_token,
        connectionType: "webrtc",
        dynamicVariables: credential.dynamic_variables,
      });
    },
    [startSession],
  );

  const start = useCallback(async () => {
    if (!dataMode) {
      setError("Choose whether this is a fictional role-play or your real redacted move.");
      return;
    }
    failedRef.current = false;
    connectedRef.current = false;
    stopPolling();
    setError(null);
    setJobSpec(null);
    setJobId(null);
    setMissingFields([]);
    setTurns([]);
    seenTurnsRef.current.clear();
    sessionIdRef.current = null;

    try {
      const status = await getIntegrationStatus();
      if (!status.live_voice.enabled || !status.live_voice.configured) {
        fail("Live voice is not available yet. Switch to Demo Mode or try again later.");
        return;
      }

      setPhase("requesting_microphone");
      if (!navigator.mediaDevices?.getUserMedia) {
        fail("This browser does not support microphone access. Try Chrome, Edge, or Safari.");
        return;
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());

      await connect(await createIntakeSession(dataMode));
    } catch (caught) {
      fail(publicError(caught));
    }
  }, [connect, dataMode, fail, stopPolling]);

  const end = useCallback(() => {
    if (phase !== "connected" && phase !== "connecting") return;
    endSession();
    beginFinalizing();
  }, [beginFinalizing, endSession, phase]);

  const retryResult = useCallback(async () => {
    const sessionId = sessionIdRef.current;
    if (!sessionId || pollingRef.current) return;
    setError(null);
    setPhase("finalizing");
    pollingRef.current = true;
    try {
      const current = await getIntakeSession(sessionId);
      if (applySession(current)) return;
      const recovered = await recoverIntakeSession(sessionId);
      if (applySession(recovered)) return;
    } catch {
      // Keep the explicit unavailable state; never restart an unbounded poll loop.
    }
    pollingRef.current = false;
    if (!mountedRef.current) return;
    setError("A final provider result is still unavailable. You can retry or start over.");
    setPhase("unavailable");
  }, [applySession]);

  const continueSpeaking = useCallback(async () => {
    const sessionId = sessionIdRef.current;
    if (!sessionId || phase !== "incomplete" || isActionPending) return;
    setIsActionPending(true);
    setError(null);
    failedRef.current = false;
    connectedRef.current = false;
    try {
      await connect(await resumeIntakeSession(sessionId));
    } catch {
      setError("The continuation could not start. Your partial draft is still safe; try again.");
      setPhase("incomplete");
    } finally {
      if (mountedRef.current) setIsActionPending(false);
    }
  }, [connect, isActionPending, phase]);

  const finishManually = useCallback(async () => {
    const sessionId = sessionIdRef.current;
    if (!sessionId || phase !== "incomplete" || isActionPending) return;
    setIsActionPending(true);
    setError(null);
    try {
      const record = await finishIntakeManually(sessionId);
      setJobSpec(record.job_spec);
      setJobId(record.job_spec.job_id ?? null);
      setPhase("completed");
    } catch {
      setError("The manual editor could not be opened. Your partial draft is still safe; retry.");
    } finally {
      if (mountedRef.current) setIsActionPending(false);
    }
  }, [isActionPending, phase]);

  const startOver = useCallback(() => {
    failedRef.current = false;
    connectedRef.current = false;
    stopPolling();
    endSession();
    sessionIdRef.current = null;
    setPhase("ready");
    setDataMode(null);
    setTurns([]);
    setJobSpec(null);
    setJobId(null);
    setMissingFields([]);
    setError(null);
    setIsActionPending(false);
    seenTurnsRef.current.clear();
  }, [endSession, stopPolling]);

  return {
    phase,
    dataMode,
    setDataMode,
    turns,
    jobSpec,
    jobId,
    missingFields,
    error,
    isActionPending,
    isAgentSpeaking: mode === "speaking",
    start,
    end,
    retryResult,
    continueSpeaking,
    finishManually,
    startOver,
  };
}
