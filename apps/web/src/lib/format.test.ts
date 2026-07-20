import { describe, expect, it } from "vitest";
import { longDate } from "./format";

describe("longDate", () => {
  it("formats a date-only value as the same local calendar day", () => {
    expect(longDate("2026-08-16")).toBe("August 16, 2026");
  });

  it("returns an unparseable value unchanged", () => {
    expect(longDate("not-a-date")).toBe("not-a-date");
  });
});
