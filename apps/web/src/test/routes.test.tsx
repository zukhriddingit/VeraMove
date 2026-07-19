import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { api } from "../api/client";

describe("VeraMove routes", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders the homepage, demo status, and API health", async () => {
    vi.spyOn(api, "health").mockResolvedValue({
      status: "ok",
      mode: "mock",
      service: "veramove-api",
    });
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRoutes />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "VeraMove" })).toBeInTheDocument();
    expect(screen.getByText("Demo mode")).toBeInTheDocument();
    expect(await screen.findByText("API connected")).toBeInTheDocument();
  });

  it("renders the intake placeholder without credentials", () => {
    render(
      <MemoryRouter initialEntries={["/intake"]}>
        <AppRoutes />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Voice or document intake" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create synthetic job" })).toBeInTheDocument();
  });

  it("enables the submit button immediately in voice intake mode", () => {
    render(
      <MemoryRouter initialEntries={["/intake"]}>
        <AppRoutes />
      </MemoryRouter>,
    );
    expect(screen.getByRole("button", { name: "Voice intake" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create synthetic job" })).toBeEnabled();
  });

  it("disables the submit button in document mode until a file is selected", () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/intake"]}>
        <AppRoutes />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Document upload" }));
    expect(screen.getByRole("button", { name: "Create synthetic job" })).toBeDisabled();

    const file = new File(["synthetic"], "quote.pdf", { type: "application/pdf" });
    const input = container.querySelector("input[type='file']") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    expect(screen.getByText(/Selected: quote\.pdf/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create synthetic job" })).toBeEnabled();
  });

  it("renders a typed loading state while a job request is pending", () => {
    vi.spyOn(api, "getJob").mockReturnValue(new Promise(() => undefined));
    render(
      <MemoryRouter initialEntries={["/confirm/11111111-1111-4111-8111-111111111111"]}>
        <AppRoutes />
      </MemoryRouter>,
    );
    expect(screen.getByText("Loading JobSpec…")).toBeInTheDocument();
  });

  it("renders an error state when a job cannot be loaded", async () => {
    vi.spyOn(api, "getJob").mockRejectedValue(new Error("Job not found"));
    render(
      <MemoryRouter initialEntries={["/confirm/missing"]}>
        <AppRoutes />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Job not found");
  });

  it("surfaces hidden fees and red flags on the calls page", async () => {
    vi.spyOn(api, "getJob").mockResolvedValue({
      job_spec: {
        job_id: "11111111-1111-4111-8111-111111111111",
        confirmed: true,
      },
      state: "quotes_ready",
      created_at: "2026-07-01T00:00:00Z",
      updated_at: "2026-07-01T00:00:00Z",
      quotes: [
        {
          quote_id: "quote-1",
          job_id: "11111111-1111-4111-8111-111111111111",
          job_spec_version: "1.0",
          vendor: { vendor_id: "vendor-1", name: "BudgetLift Moving" },
          currency: "USD",
          original_total: "2200.00",
          negotiated_total: "2500.00",
          deposit: "500.00",
          binding_type: "non_binding",
          availability: "Flexible",
          verification_status: "partially_verified",
          red_flags: ["Headline price omitted stairs, long-carry, and fuel fees"],
          fee_line_items: [
            {
              description: "Stairs fee revealed after questioning",
              amount: "250.00",
              category: "labor",
              disclosed_upfront: false,
            },
            {
              description: "Base moving labor",
              amount: "1800.00",
              category: "labor",
              disclosed_upfront: true,
            },
          ],
        },
      ],
    } as any);

    render(
      <MemoryRouter initialEntries={["/calls/11111111-1111-4111-8111-111111111111"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByText("BudgetLift Moving")).toBeInTheDocument();
    expect(screen.getByText("Red flags")).toBeInTheDocument();
    expect(screen.getByText(/Headline price omitted stairs/)).toBeInTheDocument();
    expect(screen.getByText(/Hidden fees found \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Stairs fee revealed after questioning/)).toBeInTheDocument();
  });
});
