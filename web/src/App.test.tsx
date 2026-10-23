import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import App from "./App";

describe("PHALANX Dashboard App", () => {
  it("renders header, brand, and role switcher", () => {
    render(<App />);
    expect(screen.getByText("PHALANX")).toBeInTheDocument();
    expect(screen.getByText("PAYPAL SANDBOX GUARD ACTIVE")).toBeInTheDocument();
    expect(screen.getByText("PRINCIPAL")).toBeInTheDocument();
    expect(screen.getByText("AGENT")).toBeInTheDocument();
    expect(screen.getByText("APPROVER")).toBeInTheDocument();
    expect(screen.getByText("AUDITOR")).toBeInTheDocument();
  });

  it("renders the 4 operational tabs", () => {
    render(<App />);
    expect(screen.getByText(/Scene 1: Request Console/i)).toBeInTheDocument();
    expect(screen.getByText(/Scene 2: Step-Up Approvals/i)).toBeInTheDocument();
    expect(screen.getByText(/Scene 3: Cryptographic Audit Ledger/i)).toBeInTheDocument();
    expect(screen.getByText(/Ed25519 Mandate/i)).toBeInTheDocument();
  });

  it("Scene 1: Request Console renders presets and submits intent", () => {
    render(<App />);
    expect(screen.getByText("Agent Intent Proposer")).toBeInTheDocument();
    expect(screen.getByText("Extracted Transaction Draft")).toBeInTheDocument();

    // Verify presets exist
    expect(screen.getByText("Under Limit ($25 - ALLOW)")).toBeInTheDocument();
    expect(screen.getByText("Step-Up ($1,200 - REVIEW)")).toBeInTheDocument();
    expect(screen.getByText("Over Limit ($9,500 - DENY)")).toBeInTheDocument();
    expect(screen.getByText("Prompt Injection Test")).toBeInTheDocument();

    // Submit button exists
    const submitBtn = screen.getByText("Evaluate & Submit Intent to Policy Core");
    expect(submitBtn).toBeInTheDocument();
  });

  it("Scene 2: Step-Up Approvals displays pending items and enforces agent role lock", async () => {
    render(<App />);
    const approvalsTab = screen.getByText(/Scene 2: Step-Up Approvals/i);
    fireEvent.click(approvalsTab);

    // Verify pending item is displayed
    expect(screen.getByText("req_stepup_1001")).toBeInTheDocument();
    expect(screen.getByText("Authorize Transaction")).toBeInTheDocument();
    expect(screen.getByText("Deny Exception")).toBeInTheDocument();

    // Switch persona to AGENT
    const agentRadio = screen.getByText("AGENT");
    fireEvent.click(agentRadio);

    // Verify warning banner and button disabling
    await waitFor(() => {
      expect(
        screen.getByText(/Role: AGENT — Approval actions disabled/i)
      ).toBeInTheDocument();
      const approveBtn = screen.getByText("Authorize Transaction").closest("button");
      expect(approveBtn).toBeDisabled();
    });
  });

  it("Scene 3: Cryptographic Audit Ledger renders block chain and verify button", () => {
    render(<App />);
    const ledgerTab = screen.getByText(/Scene 3: Cryptographic Audit Ledger/i);
    fireEvent.click(ledgerTab);

    expect(screen.getByText("Cryptographic Shield-Wall Ledger")).toBeInTheDocument();
    expect(screen.getByText(/Verify Chain/i)).toBeInTheDocument();
    expect(screen.getByText("Simulate Database Tamper")).toBeInTheDocument();
    expect(screen.getByText("Block #1")).toBeInTheDocument();
    expect(screen.getByText("Block #2")).toBeInTheDocument();
    expect(screen.getByText("Block #3")).toBeInTheDocument();
  });

  it("Mandate view displays Ed25519 parameters and remaining budget", () => {
    render(<App />);
    const mandateTab = screen.getByText(/Ed25519 Mandate/i);
    fireEvent.click(mandateTab);

    expect(screen.getByText("Active Ed25519 Authority Mandate")).toBeInTheDocument();
    expect(screen.getByText(/mandate_default_sandbox/i)).toBeInTheDocument();
    expect(screen.getByText("Remaining Budget")).toBeInTheDocument();
    expect(screen.getByText(/Single Transaction Cap/i)).toBeInTheDocument();
    expect(screen.getByText(/Instant Autonomous Threshold/i)).toBeInTheDocument();
    expect(screen.getByText(/Lifetime Budget Cap/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Signature is an integrity seal, not human non-repudiation/i)
    ).toBeInTheDocument();
  });
});
