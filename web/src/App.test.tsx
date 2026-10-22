import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import App from "./App";

describe("PHALANX Dashboard App", () => {
  it("renders header and brand title", () => {
    render(<App />);
    expect(screen.getByText("PHALANX")).toBeInTheDocument();
    expect(screen.getByText("SANDBOX GUARD ACTIVE")).toBeInTheDocument();
  });

  it("renders KPI summary cards", () => {
    render(<App />);
    expect(screen.getByText("Autonomous Authorizations")).toBeInTheDocument();
    expect(screen.getByText("Audit Ledger Events")).toBeInTheDocument();
  });
});
