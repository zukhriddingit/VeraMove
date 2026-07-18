import { render, screen } from "@testing-library/react";
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
});
