import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import App from "./App";

describe("PHALANX PayPal-Inspired Shell & Navigation", () => {
  it("renders topbar with brand wordmark, sandbox guard, and footer disclaimer", () => {
    render(<App />);
    expect(screen.getByText("PHALANX")).toBeInTheDocument();
    expect(screen.getByText("SANDBOX")).toBeInTheDocument();
    expect(screen.getByText("Not affiliated with PayPal.")).toBeInTheDocument();
  });

  it("renders Home screen by default with three numbers and primary action", () => {
    render(<App />);
    expect(screen.getByText("REMAINING AUTHORITY")).toBeInTheDocument();
    expect(screen.getByText("PENDING APPROVALS")).toBeInTheDocument();
    expect(screen.getByText("LAST RECORDED ACTIVITY")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Pay & Request/i })[0]).toBeInTheDocument();
  });

  it("navigates to Pay screen and renders presets and submit button", () => {
    render(<App />);
    const payBtns = screen.getAllByRole("button", { name: "Pay" });
    fireEvent.click(payBtns[0]);

    expect(screen.getByText("Scenario Presets")).toBeInTheDocument();
    expect(screen.getByText("Under Limit ($25 - ALLOW)")).toBeInTheDocument();
    expect(screen.getByText("High Value ($1,200 - STEP_UP)")).toBeInTheDocument();
    expect(screen.getByText("Over Cap ($6,000 - DENY)")).toBeInTheDocument();
    expect(screen.getByText("Evaluate & Submit Intent to Policy Core")).toBeInTheDocument();
  });

  it("navigates to Approvals screen and enforces agent role restriction", async () => {
    render(<App />);
    const approvalsBtns = screen.getAllByRole("button", { name: "Approvals" });
    fireEvent.click(approvalsBtns[0]);

    expect(screen.getByRole("heading", { name: "Human Supervisor Step-Up Review Queue" })).toBeInTheDocument();

    // Open profile menu to switch to AGENT role
    const profileBtn = screen.getByRole("button", { name: /APPROVER/i });
    fireEvent.click(profileBtn);

    const agentOption = screen.getByRole("menuitem", { name: /AGENT/i });
    fireEvent.click(agentOption);

    // Verify warning banner is displayed
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText(/Role Restriction:/i)).toBeInTheDocument();
    });
  });

  it("navigates to Activity screen and renders chain sequence and activity journal", () => {
    render(<App />);
    const activityBtns = screen.getAllByRole("button", { name: "Activity" });
    fireEvent.click(activityBtns[0]);

    expect(screen.getByRole("heading", { name: "Cryptographic Shield-Wall Ledger" })).toBeInTheDocument();
    expect(screen.getByText("Transaction Activity Journal")).toBeInTheDocument();
  });

  it("navigates to Mandates screen and renders Ed25519 parameters", () => {
    render(<App />);
    const mandatesBtns = screen.getAllByRole("button", { name: "Mandates" });
    fireEvent.click(mandatesBtns[0]);

    expect(screen.getByRole("heading", { name: "Ed25519 Authority Mandate" })).toBeInTheDocument();
    expect(screen.getByText("SINGLE TRANSACTION CAP")).toBeInTheDocument();
    expect(screen.getByText("INSTANT AUTONOMOUS THRESHOLD")).toBeInTheDocument();
  });

  it("navigates to Attack Lab screen and displays threat vectors", () => {
    render(<App />);
    const attackLabBtns = screen.getAllByRole("button", { name: "Attack Lab" });
    fireEvent.click(attackLabBtns[0]);

    expect(screen.getByRole("heading", { name: "Adversarial Attack Simulation Lab" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Run Attack Lab/i })).toBeInTheDocument();
    expect(screen.getByText("PROMPT INJECTION")).toBeInTheDocument();
    expect(screen.getByText("PAYEE SWAP")).toBeInTheDocument();
  });

  it("switches theme between light and dark", () => {
    render(<App />);
    const themeBtn = screen.getByLabelText(/Switch to dark theme/i);
    fireEvent.click(themeBtn);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");

    const lightBtn = screen.getByLabelText(/Switch to light theme/i);
    fireEvent.click(lightBtn);
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });
});
