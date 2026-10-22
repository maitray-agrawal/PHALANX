import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import App from "./App";

describe("PHALANX Dashboard App", () => {
  it("renders header, brand, and role switcher", () => {
    render(<App />);
    expect(screen.getByText("PHALANX")).toBeInTheDocument();
    expect(screen.getByText("PAYPAL SANDBOX GUARD ACTIVE")).toBeInTheDocument();
    expect(screen.getByText("PRINCIPAL")).toBeInTheDocument();
    expect(screen.getByText("AGENT")).toBeInTheDocument();
  });

  it("renders the 4 operational tabs", () => {
    render(<App />);
    expect(screen.getByText(/Scene 1: Request Console/i)).toBeInTheDocument();
    expect(screen.getByText(/Scene 2: Step-Up Approvals/i)).toBeInTheDocument();
    expect(screen.getByText(/Scene 3: Cryptographic Audit Ledger/i)).toBeInTheDocument();
    expect(screen.getByText(/Ed25519 Mandate/i)).toBeInTheDocument();
  });

  it("switches tabs and displays scene content", () => {
    render(<App />);
    const mandateTab = screen.getByText(/Ed25519 Mandate/i);
    fireEvent.click(mandateTab);
    expect(screen.getByText("Active Ed25519 Authority Mandate")).toBeInTheDocument();
    expect(screen.getByText("mandate_default_astra (v1)")).toBeInTheDocument();
  });
});
