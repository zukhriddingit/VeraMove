import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/api/client";

describe("browser voice API operations", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses the centralized client for the complete secure session lifecycle", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            live_voice: { configured: true, enabled: true },
            openai: { configured: true, enabled: true, usage: [] },
            supabase: { configured: true, enabled: true },
            tavily: { configured: true, enabled: true },
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            intake_session_id: "11111111-1111-4111-8111-111111111111",
            job_id: "22222222-2222-4222-8222-222222222222",
            status: "pending",
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            conversation_token: "ephemeral-test-token",
            dynamic_variables: {
              intake_session_id: "11111111-1111-4111-8111-111111111111",
              job_id: "22222222-2222-4222-8222-222222222222",
              agent_config_version: "intake-v1",
            },
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            intake_session_id: "11111111-1111-4111-8111-111111111111",
            job_id: "22222222-2222-4222-8222-222222222222",
            conversation_id: "conv_example_123",
            status: "in_progress",
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            intake_session_id: "11111111-1111-4111-8111-111111111111",
            job_id: "22222222-2222-4222-8222-222222222222",
            status: "completed",
          }),
          { status: 200 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    await apiClient.integrationStatus();
    const session = await apiClient.createIntakeSession();
    await apiClient.issueBrowserVoiceToken(session.intake_session_id);
    await apiClient.attachIntakeConversation(session.intake_session_id, "conv_example_123");
    await apiClient.getIntakeSession(session.intake_session_id);

    expect(fetchMock.mock.calls.map(([url]) => new URL(String(url)).pathname)).toEqual([
      "/api/integrations/status",
      "/api/intake/sessions",
      "/api/intake/sessions/11111111-1111-4111-8111-111111111111/voice-token",
      "/api/intake/sessions/11111111-1111-4111-8111-111111111111/conversation",
      "/api/intake/sessions/11111111-1111-4111-8111-111111111111",
    ]);
    expect(JSON.parse(fetchMock.mock.calls[3][1]?.body as string)).toEqual({
      conversation_id: "conv_example_123",
    });
  });
});
