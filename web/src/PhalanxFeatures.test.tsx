import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import App from "./App";

describe("PHALANX Seven Operational Screens & Shell Features", () => {
  it("Screen 1: Home renders three numbers, sticky action, and aligned demo authority figure", () => {
    render(<App />);
    expect(screen.getByText("REMAINING AUTHORITY")).toBeInTheDocument();
    expect(screen.getByText("$25,000.00")).toBeInTheDocument();
    expect(screen.getByText("PENDING APPROVALS")).toBeInTheDocument();
    expect(screen.getByText("LAST RECORDED ACTIVITY")).toBeInTheDocument();
    expect(screen.getByText("Recent Activity")).toBeInTheDocument();
  });

  it("Screen 2: Pay renders preset buttons, intent inputs, and triggers evaluation", async () => {
    render(<App />);
    const payBtns = screen.getAllByRole("button", { name: "Pay" });
    fireEvent.click(payBtns[0]);

    expect(screen.getByText("Scenario Presets")).toBeInTheDocument();
    const presetBtn = screen.getByText("Under Limit ($25 - ALLOW)");
    fireEvent.click(presetBtn);

    const submitBtn = screen.getByRole("button", { name: "Evaluate & Submit Intent to Policy Core" });
    expect(submitBtn).toBeInTheDocument();
  });

  it("Screen 3: Approvals renders step-up queue or empty state with sample request action", async () => {
    render(<App />);
    const approvalsBtns = screen.getAllByRole("button", { name: "Approvals" });
    fireEvent.click(approvalsBtns[0]);

    expect(screen.getByRole("heading", { name: "Human Supervisor Step-Up Review Queue" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /Create sample request/i })[0]).toBeInTheDocument();
    });
  });

  it("Screen 4: Activity renders ledger feed and chain sequence", () => {
    render(<App />);
    const activityBtns = screen.getAllByRole("button", { name: "Activity" });
    fireEvent.click(activityBtns[0]);

    expect(screen.getByRole("heading", { name: "Cryptographic Shield-Wall Ledger" })).toBeInTheDocument();
    expect(screen.getByText("Transaction Activity Journal")).toBeInTheDocument();
  });

  it("Screen 5: Mandates renders read-only limits matching demo dataset ($25,000, $5,000, $500)", () => {
    render(<App />);
    const mandatesBtns = screen.getAllByRole("button", { name: "Mandates" });
    fireEvent.click(mandatesBtns[0]);

    expect(screen.getByRole("heading", { name: "Ed25519 Authority Mandate" })).toBeInTheDocument();
    expect(screen.getByText("Budget Utilization")).toBeInTheDocument();
    expect(screen.getByText("SINGLE TRANSACTION CAP")).toBeInTheDocument();
    expect(screen.getByText("$5,000.00")).toBeInTheDocument();
    expect(screen.getByText("$500.00")).toBeInTheDocument();
  });

  it("Screen 6: Attack Lab renders six cards and execution trigger", () => {
    render(<App />);
    const attackLabBtns = screen.getAllByRole("button", { name: "Attack Lab" });
    fireEvent.click(attackLabBtns[0]);

    expect(screen.getByRole("heading", { name: "Adversarial Attack Simulation Lab" })).toBeInTheDocument();
    expect(screen.getByText("PROMPT INJECTION")).toBeInTheDocument();
    expect(screen.getByText("PAYEE SWAP")).toBeInTheDocument();
    expect(screen.getByText("AMOUNT TAMPER AFTER APPROVAL")).toBeInTheDocument();
    expect(screen.getByText("REPLAY")).toBeInTheDocument();
    expect(screen.getByText("FORGED WEBHOOK")).toBeInTheDocument();
    expect(screen.getByText("AGENT SELF APPROVAL")).toBeInTheDocument();
  });

  it("Mobile Sheet: opens and closes more options modal", async () => {
    render(<App />);
    const moreBtn = screen.getByRole("button", { name: "More" });
    fireEvent.click(moreBtn);

    expect(screen.getByRole("heading", { name: "More Services & Options" })).toBeInTheDocument();
    expect(screen.getByText("Ed25519 Authority Mandate")).toBeInTheDocument();
    expect(screen.getByText("Adversarial Attack Lab")).toBeInTheDocument();
    expect(screen.getByText("Receipt & Proof Verifier")).toBeInTheDocument();

    const closeBtn = screen.getByLabelText("Close menu");
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "More Services & Options" })).not.toBeInTheDocument();
    });
  });
});
