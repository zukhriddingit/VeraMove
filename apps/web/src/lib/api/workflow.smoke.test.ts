import { afterEach, describe, expect, it, vi } from "vitest";
import { jobActions } from "./actions";
import * as demo from "./demo/adapter";
import {
  DEMO_JOB_ID,
  demoJobSpecMissing,
} from "./demo/fixtures";

async function advance<T>(promise: Promise<T>, milliseconds: number): Promise<T> {
  await vi.advanceTimersByTimeAsync(milliseconds);
  return promise;
}

describe("VeraMove workflow smoke tests", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("completes Demo mode through the evidence-backed report", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-19T01:00:00Z"));

    await advance(demo.createJobFromVoice("clean"), 400);
    await advance(demo.confirmJob(DEMO_JOB_ID), 200);
    await advance(demo.startCalls(DEMO_JOB_ID), 200);

    await vi.advanceTimersByTimeAsync(1_500);
    const calls = await advance(demo.getCalls(DEMO_JOB_ID), 120);
    expect(calls).toHaveLength(3);
    expect(calls.every((call) => call.status === "completed")).toBe(true);

    const quoteReadyJob = await advance(demo.getJob(DEMO_JOB_ID), 150);
    expect(quoteReadyJob.status).toBe("quotes_ready");

    const negotiation = await advance(demo.negotiateJob(DEMO_JOB_ID), 220);
    expect(negotiation.afterTotal).toBeLessThan(negotiation.beforeTotal);
    expect(negotiation.delta).toBe(-300);

    await vi.advanceTimersByTimeAsync(1_800);
    const completedJob = await advance(demo.getJob(DEMO_JOB_ID), 150);
    expect(completedJob.status).toBe("completed");

    const report = await advance(demo.getReport(DEMO_JOB_ID), 200);
    expect(report.ranking).toHaveLength(3);
    expect(report.recommended.vendorId).toBeTruthy();
    expect(report.evidenceIndex.length).toBeGreaterThan(0);
  });

  it("blocks confirmation when required fields are missing", () => {
    expect(jobActions(demoJobSpecMissing).canConfirm).toBe(false);
  });

  it("blocks negotiation before the job reaches quotes_ready", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-19T01:00:00Z"));

    await advance(demo.createJobFromVoice("clean"), 400);
    await advance(demo.confirmJob(DEMO_JOB_ID), 200);

    const assertion = expect(demo.negotiateJob(DEMO_JOB_ID)).rejects.toThrow(
      'Cannot negotiate from state "confirmed"',
    );
    await vi.advanceTimersByTimeAsync(220);
    await assertion;
  });
});
