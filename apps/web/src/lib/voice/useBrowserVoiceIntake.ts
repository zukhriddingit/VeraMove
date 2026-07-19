import { useCallback, useEffect, useRef, useState } from "react";
import { useConversation } from "@elevenlabs/react";
import type { JobSpecV1 } from "@/api/client";
import {
  attachIntakeConversation,
  createIntakeSession,
  getIntegrationStatus,
  getIntakeSession,
  issueBrowserVoiceToken,
} from "@/lib/api/endpoints";

export type BrowserVoicePhase =
  | "ready"
  | "requesting_microphone"
  | "connecting"
  | "connected"
  | "processing"
  | "delayed"
  | "completed"
  | "failed";

export interface VoiceTurn {
  id: string;
  role: "agent" | "user";
  text: string;
}

const POLL_INTERVAL_MS = 1_500;
const MAX_POLL_ATTEMPTS = 40;

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
  const [turns, setTurns] = useState<VoiceTurn[]>([]);
  const [jobSpec, setJobSpec] = useState<JobSpecV1 | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const pollingRef = useRef(false);
  const failedRef = useRef(false);
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

  const pollForResult = useCallback(
    async (attempt = 0) => {
      const sessionId = sessionIdRef.current;
      if (!sessionId || failedRef.current || !mountedRef.current) return;
      pollingRef.current = true;

      try {
        const session = await getIntakeSession(sessionId);
        if (!mountedRef.current || failedRef.current) return;
        if (session.status === "completed" && session.job_spec) {
          stopPolling();
          setJobSpec(session.job_spec);
          setJobId(session.job_id);
          setPhase("completed");
          return;
        }
        if (session.status === "failed") {
          fail(
            "The interview ended, but its move details could not be processed. Please try again.",
          );
          return;
        }
      } catch {
        // A transient Render or network failure should not discard a finished interview.
      }

      if (attempt + 1 >= MAX_POLL_ATTEMPTS) {
        pollingRef.current = false;
        setPhase("delayed");
        return;
      }
      pollTimerRef.current = window.setTimeout(
        () => void pollForResult(attempt + 1),
        POLL_INTERVAL_MS,
      );
    },
    [fail, stopPolling],
  );

  const { startSession, endSession, mode } = useConversation({
    onConnect: ({ conversationId }) => {
      const sessionId = sessionIdRef.current;
      if (!sessionId || !mountedRef.current) return;
      setPhase("connected");
      void attachIntakeConversation(sessionId, conversationId).catch(() => {
        endSessionRef.current();
        fail("The voice interview connected but could not be securely linked. Please retry.");
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
      fail("The voice connection was interrupted. Please retry the interview.");
    },
    onDisconnect: (details) => {
      if (!mountedRef.current || failedRef.current) return;
      if (details.reason === "error") {
        fail("The voice connection was interrupted. Please retry the interview.");
        return;
      }
      setPhase("processing");
      void pollForResult();
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

  const start = useCallback(async () => {
    failedRef.current = false;
    stopPolling();
    setError(null);
    setJobSpec(null);
    setJobId(null);
    setTurns([]);
    seenTurnsRef.current.clear();
    sessionIdRef.current = null;

    try {
      const status = await getIntegrationStatus();
      if (!status.live_voice.enabled || !status.live_voice.configured) {
        fail("Live voice is not available yet. Switch to Demo Mode or try again after deployment.");
        return;
      }

      setPhase("requesting_microphone");
      if (!navigator.mediaDevices?.getUserMedia) {
        fail("This browser does not support microphone access. Try Chrome, Edge, or Safari.");
        return;
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());

      setPhase("connecting");
      const session = await createIntakeSession();
      sessionIdRef.current = session.intake_session_id;
      const credential = await issueBrowserVoiceToken(session.intake_session_id);
      startSession({
        conversationToken: credential.conversation_token,
        connectionType: "webrtc",
        dynamicVariables: credential.dynamic_variables,
      });
    } catch (caught) {
      fail(publicError(caught));
    }
  }, [fail, startSession, stopPolling]);

  const end = useCallback(() => {
    if (phase !== "connected" && phase !== "connecting") return;
    setPhase("processing");
    endSession();
  }, [endSession, phase]);

  const retryResult = useCallback(() => {
    if (!sessionIdRef.current || pollingRef.current) return;
    setPhase("processing");
    void pollForResult();
  }, [pollForResult]);

  const reset = useCallback(() => {
    failedRef.current = false;
    stopPolling();
    endSession();
    sessionIdRef.current = null;
    setPhase("ready");
    setTurns([]);
    setJobSpec(null);
    setJobId(null);
    setError(null);
    seenTurnsRef.current.clear();
  }, [endSession, stopPolling]);

  return {
    phase,
    turns,
    jobSpec,
    jobId,
    error,
    isAgentSpeaking: mode === "speaking",
    start,
    end,
    reset,
    retryResult,
  };
}
