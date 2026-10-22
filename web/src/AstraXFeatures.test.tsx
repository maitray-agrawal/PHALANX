import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import App from "./App";

describe("AstraX Intelligence & Operational Extensions", () => {
  it("renders Overview tab with cockpit metrics and architecture pipeline", () => {
    render(<App />);
    const overviewTab = screen.getByRole("tab", { name: "Overview" });
    fireEvent.click(overviewTab);

    expect(screen.getByText("AstraX Operational Authorization Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Intent Delimiters")).toBeInTheDocument();
    expect(screen.getByText("Pure Policy Core")).toBeInTheDocument();
    expect(screen.getByText("Autonomous Allow")).toBeInTheDocument();
    expect(screen.getByText("66.7%")).toBeInTheDocument();
    expect(screen.getByText("Adversarial Blocks")).toBeInTheDocument();
    expect(screen.getByText("67 / 67")).toBeInTheDocument();
  });

  it("renders Rail Reconciliation tab and executes resolution actions", async () => {
    render(<App />);
    const reconcileTab = screen.getByRole("tab", { name: /Rail Reconciliation/i });
    fireEvent.click(reconcileTab);

    expect(screen.getByText(/Ambiguous Rail Reconciliation/i)).toBeInTheDocument();
    expect(screen.getByText("req_ambiguous_7701")).toBeInTheDocument();
    expect(screen.getByText("$450.00 USD")).toBeInTheDocument();

    // Click Confirm Success
    const confirmBtn = screen.getByText("Confirm Success");
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByText(/transitioned to SETTLED/i)).toBeInTheDocument();
    });

    // Trigger simulation
    const simulateBtn = screen.getByText(/\+ Simulate PayPal 504 Gateway Timeout Event/i);
    fireEvent.click(simulateBtn);

    expect(screen.getByText(/Simulated PayPal 504 Timeout/i)).toBeInTheDocument();
  });

  it("renders Security Center with red team invariants", () => {
    render(<App />);
    const secTab = screen.getByRole("tab", { name: "Security Center" });
    fireEvent.click(secTab);

    expect(screen.getByText(/PHALANX Security Invariants & Red Team Posture/i)).toBeInTheDocument();
    expect(screen.getByText("Pure Domain Core")).toBeInTheDocument();
    expect(screen.getByText("Zero LLM in Auth Path")).toBeInTheDocument();
    expect(screen.getByText("Atomic Concurrent Idempotency (F4)")).toBeInTheDocument();
    expect(screen.getByText("Persistent Budget Accounting (F5)")).toBeInTheDocument();
    expect(screen.getByText("Ambiguous Rail Hold (F6)")).toBeInTheDocument();
    expect(screen.getByText("Shield-Wall Audit Ledger")).toBeInTheDocument();
  });

  it("renders Developer & MCP Tools Catalog", () => {
    render(<App />);
    const devTab = screen.getByRole("tab", { name: "Developer & MCP" });
    fireEvent.click(devTab);

    expect(screen.getByText(/Model Context Protocol \(MCP\) & Developer Integration/i)).toBeInTheDocument();
    expect(screen.getByText("tool: phalanx_authorize_transaction")).toBeInTheDocument();
    expect(screen.getByText("tool: phalanx_get_mandate")).toBeInTheDocument();
  });

  it("switches theme mode via ThemeSwitcher", () => {
    render(<App />);
    const lightBtn = screen.getByRole("radio", { name: /Light/i });
    const darkBtn = screen.getByRole("radio", { name: /Dark/i });

    fireEvent.click(darkBtn);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");

    fireEvent.click(lightBtn);
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });
});
