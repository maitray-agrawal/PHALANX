import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PillButton } from "./PillButton";
import { DecisionBadge } from "./DecisionBadge";
import { EmptyState } from "./EmptyState";
import { Skeleton } from "./Skeleton";
import { Toast } from "./Toast";
import { RequestCard } from "./RequestCard";
import { ApprovalCard } from "./ApprovalCard";
import { ActivityRow } from "./ActivityRow";
import { ReceiptCard } from "./ReceiptCard";
import { MandateMeter } from "./MandateMeter";
import { ChainStrip } from "./ChainStrip";

describe("PHALANX PayPal-Inspired Component Set", () => {
  it("renders PillButton with gold primary and handles click", () => {
    const handleClick = vi.fn();
    render(
      <PillButton variant="primary" onClick={handleClick}>
        Send Money
      </PillButton>
    );
    const btn = screen.getByRole("button", { name: "Send Money" });
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveClass("pill-button-primary");
    fireEvent.click(btn);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it("renders PillButton secondary blue outline and loading state", () => {
    render(
      <PillButton variant="secondary" loading={true}>
        Authorize
      </PillButton>
    );
    const btn = screen.getByRole("button", { name: "Authorize" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveClass("pill-button-secondary");
    expect(btn).toHaveClass("is-loading");
  });

  it("renders DecisionBadge correctly for ALLOW, STEP_UP, and DENY", () => {
    const { rerender } = render(<DecisionBadge decision="ALLOW" />);
    expect(screen.getByText("ALLOW")).toBeInTheDocument();

    rerender(<DecisionBadge decision="STEP_UP" />);
    expect(screen.getByText("STEP_UP")).toBeInTheDocument();

    rerender(<DecisionBadge decision="DENY" />);
    expect(screen.getByText("DENY")).toBeInTheDocument();
  });

  it("renders EmptyState with icon, title, description, and next step action", () => {
    const handleAction = vi.fn();
    render(
      <EmptyState
        title="No pending step-ups"
        description="All requests have been reviewed."
        actionLabel="Make Request"
        onAction={handleAction}
      />
    );
    expect(screen.getByText("No pending step-ups")).toBeInTheDocument();
    expect(screen.getByText("All requests have been reviewed.")).toBeInTheDocument();
    const btn = screen.getByRole("button", { name: "Make Request" });
    fireEvent.click(btn);
    expect(handleAction).toHaveBeenCalledTimes(1);
  });

  it("renders Skeleton loading placeholder", () => {
    const { container } = render(<Skeleton height="32px" width="120px" />);
    const el = container.querySelector(".skeleton-shimmer");
    expect(el).toBeInTheDocument();
    expect(el).toHaveStyle({ height: "32px", width: "120px" });
  });

  it("renders Toast and handles dismiss", () => {
    const handleDismiss = vi.fn();
    render(
      <Toast
        type="success"
        message="Transaction approved and submitted"
        onDismiss={handleDismiss}
        durationMs={0}
      />
    );
    expect(screen.getByText("Transaction approved and submitted")).toBeInTheDocument();
    const closeBtn = screen.getByRole("button", { name: "Dismiss notification" });
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it("renders RequestCard with formatted money and decision badge", () => {
    render(
      <RequestCard
        agentId="agent-auto-1"
        recipientId="vendor-paypal-sandbox-1"
        amountMinor={2500}
        currency="USD"
        purpose="Server capacity reserve"
        idempotencyKey="tx_req_1001"
        decision="ALLOW"
        payoutId="sandbox_tx_12345"
      />
    );
    expect(screen.getByText("$25.00")).toBeInTheDocument();
    expect(screen.getByText("vendor-paypal-sandbox-1")).toBeInTheDocument();
    expect(screen.getByText("ALLOW")).toBeInTheDocument();
    expect(screen.getByText(/sandbox_tx_12345/)).toBeInTheDocument();
  });

  it("renders ApprovalCard with digest inspection and handles approval action", () => {
    const onApprove = vi.fn();
    const onDecline = vi.fn();
    render(
      <ApprovalCard
        requestId="req_stepup_1001"
        agentId="agent-auto-1"
        recipientId="vendor-1"
        amountMinor={120000}
        currency="USD"
        purpose="High capacity compute nodes"
        intentDigest="a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"
        createdAtUtc="2026-10-22T12:00:00Z"
        isAgentRole={false}
        onApprove={onApprove}
        onDecline={onDecline}
      />
    );
    expect(screen.getByText("$1,200.00")).toBeInTheDocument();
    expect(screen.getByText("req_stepup_1001")).toBeInTheDocument();

    const approveBtn = screen.getByRole("button", { name: "Authorize Transaction" });
    fireEvent.click(approveBtn);
    expect(onApprove).toHaveBeenCalledWith(
      "req_stepup_1001",
      "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"
    );
  });

  it("disables approval buttons when isAgentRole is true", () => {
    render(
      <ApprovalCard
        requestId="req_stepup_1001"
        agentId="agent-auto-1"
        recipientId="vendor-1"
        amountMinor={120000}
        currency="USD"
        purpose="Compute nodes"
        intentDigest={"0000".repeat(16)}
        createdAtUtc="2026-10-22T12:00:00Z"
        isAgentRole={true}
        onApprove={vi.fn()}
        onDecline={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: "Authorize Transaction" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Decline" })).toBeDisabled();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("renders ActivityRow with provider state and triggers view receipt", () => {
    const handleViewReceipt = vi.fn();
    render(
      <ActivityRow
        receiptId="rcpt_evt_000001_8a12f901"
        decision="ALLOW"
        amountMinor={2500}
        currency="USD"
        payee="vendor-paypal-sandbox-1"
        reasonCode="PRE_AUTHORIZED"
        providerState="COMPLETED"
        timestampUtc="2026-10-22T12:00:00Z"
        onViewReceipt={handleViewReceipt}
      />
    );
    expect(screen.getByText("$25.00")).toBeInTheDocument();
    expect(screen.getByText("vendor-paypal-sandbox-1")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("PRE_AUTHORIZED")).toBeInTheDocument();

    const receiptBtn = screen.getByTitle(/View cryptographic receipt/);
    fireEvent.click(receiptBtn);
    expect(handleViewReceipt).toHaveBeenCalledWith("rcpt_evt_000001_8a12f901");
  });

  it("renders MandateMeter with utilization calculations", () => {
    render(
      <MandateMeter
        mandate={{
          mandate_id: "mandate_default_sandbox",
          version: 1,
          principal_id: "principal_treasury",
          agent_id: "agent-auto-1",
          single_limit_minor: 500000,
          instant_threshold_minor: 50000,
          lifetime_budget_minor: 2500000,
          spent_budget_minor: 25000,
          remaining_budget_minor: 2475000,
          currency: "USD",
          allowed_payees: ["vendor-paypal-sandbox-1"],
          allowed_purposes: ["cloud compute"],
          valid_from_utc: "2026-10-22T00:00:00Z",
          valid_until_utc: "2027-03-31T23:59:59Z",
          status: "ACTIVE",
          key_id: "key_001",
          signature: "f".repeat(128),
        }}
      />
    );
    expect(screen.getByText("Active Ed25519 Authority Mandate")).toBeInTheDocument();
    expect(screen.getByText("$5,000.00")).toBeInTheDocument();
    expect(screen.getByText("$500.00")).toBeInTheDocument();
    expect(screen.getByText("$24,750.00")).toBeInTheDocument();
  });

  it("renders ChainStrip with blocks and verify button", () => {
    const handleVerify = vi.fn();
    render(
      <ChainStrip
        events={[
          {
            event_id: "evt_000001_12345678",
            event_type: "AUTHORIZATION_EVALUATED",
            prev_hash: "0".repeat(64),
            event_hash: "a".repeat(64),
            payload: { amount_minor: 1500, decision: "ALLOW" },
          },
        ]}
        verification={{
          is_valid: true,
          message: "1/1 blocks intact",
          broken_index: null,
          total_events: 1,
        }}
        onVerify={handleVerify}
      />
    );
    expect(screen.getByText("Block #1")).toBeInTheDocument();
    expect(screen.getByText(/1\/1 blocks intact/)).toBeInTheDocument();
    const verifyBtn = screen.getByRole("button", { name: "Verify Chain" });
    fireEvent.click(verifyBtn);
    expect(handleVerify).toHaveBeenCalledTimes(1);
  });

  it("renders ReceiptCard with hash chain proof and verify action", () => {
    const handleVerify = vi.fn();
    render(
      <ReceiptCard
        receipt={{
          receipt_id: "rcpt_evt_000001_8a12f901",
          intent_digest: "d".repeat(64),
          mandate_id: "mandate_default_sandbox",
          mandate_version: 1,
          decision: "ALLOW",
          reason_codes: ["PRE_AUTHORIZED"],
          ledger_sequence: 1,
          hash_chain_proof: {
            event_id: "evt_000001_8a12f901",
            event_seq: 1,
            prev_hash: "0".repeat(64),
            event_hash: "e".repeat(64),
            canonical_payload_hash: "c".repeat(64),
            is_valid: true,
          },
          amount_minor: 2500,
          currency: "USD",
          payee: "vendor-paypal-sandbox-1",
          created_at_utc: "2026-10-22T12:00:00Z",
        }}
        onVerify={handleVerify}
      />
    );
    expect(screen.getByText("Cryptographic Transaction Receipt")).toBeInTheDocument();
    expect(screen.getByText("$25.00")).toBeInTheDocument();
    expect(screen.getByText("Link Valid")).toBeInTheDocument();
    const btn = screen.getByRole("button", { name: "Verify Receipt on Public Ledger" });
    fireEvent.click(btn);
    expect(handleVerify).toHaveBeenCalledWith("rcpt_evt_000001_8a12f901");
  });
});
