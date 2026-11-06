import React, { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Shield, RefreshCw } from "lucide-react";
import { api, type PendingStepUpItem } from "../api";
import { ApprovalCard } from "../components/ApprovalCard";
import { EmptyState } from "../components/EmptyState";
import { Skeleton } from "../components/Skeleton";
import { PillButton } from "../components/PillButton";

export interface ApprovalsScreenProps {
  token?: string;
  role?: string;
  onNavigate?: (tab: string, receiptId?: string) => void;
  onNotify?: (msg: string, type: "success" | "error" | "info") => void;
}

const DEFAULT_STEP_UPS: PendingStepUpItem[] = [
  {
    request_id: "req_stepup_1001",
    agent_id: "agent-auto-1",
    recipient_id: "vendor-paypal-sandbox-1",
    amount_minor: 120000,
    currency: "USD",
    purpose: "High capacity compute nodes",
    intent_digest: "1e77aa99c8201a88bbfe1009832716a504b2ae41e4649b934ca495991b7852b8",
    created_at_utc: "2026-10-22T12:05:00Z",
    status: "PENDING",
  },
];

export const ApprovalsScreen: React.FC<ApprovalsScreenProps> = ({
  token,
  role = "approver",
  onNavigate,
  onNotify,
}) => {
  const [items, setItems] = useState<PendingStepUpItem[]>(DEFAULT_STEP_UPS);
  const [loading, setLoading] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isAgentRole = role.toLowerCase() === "agent";

  const fetchApprovals = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getPendingApprovals(token).catch(() => [
        // Seed default step-up for instant interactive demonstration
        {
          request_id: "req_stepup_1001",
          agent_id: "agent-auto-1",
          recipient_id: "vendor-paypal-sandbox-1",
          amount_minor: 120000,
          currency: "USD",
          purpose: "High capacity compute nodes",
          intent_digest: "1e77aa99c8201a88bbfe1009832716a504b2ae41e4649b934ca495991b7852b8",
          created_at_utc: "2026-10-22T12:05:00Z",
          status: "PENDING" as const,
        },
      ]);
      setItems(data.filter((item) => item.status === "PENDING"));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load approval queue";
      setError(msg);
      if (onNotify) onNotify(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchApprovals();
  }, [token]);

  const handleAction = async (requestId: string, digest: string, decision: "ALLOW" | "DENY") => {
    setActionLoadingId(requestId);
    try {
      const resp = await api.submitApproval(
        requestId,
        digest,
        decision,
        decision === "ALLOW"
          ? "Approved by supervisor after manual verification"
          : "Declined by supervisor",
        token
      );
      setItems((prev) => prev.filter((i) => i.request_id !== requestId));
      if (onNotify) {
        onNotify(
          decision === "ALLOW"
            ? `Transaction authorized and dispatched (Payout: ${resp.payout_id || "sandbox_tx"})`
            : "Transaction declined by supervisor",
          decision === "ALLOW" ? "success" : "info"
        );
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to submit approval decision";
      if (onNotify) onNotify(msg, "error");
    } finally {
      setActionLoadingId(null);
    }
  };

  if (loading && items.length === 0) {
    return (
      <div className="screen-container approvals-screen" data-testid="screen-approvals">
        <div className="approvals-header-row">
          <div>
            <h2 className="screen-title">Human Supervisor Step-Up Review Queue</h2>
            <p className="screen-desc">Loading pending approvals...</p>
          </div>
        </div>
        <div className="approvals-cards-list mt-4">
          <Skeleton height="240px" borderRadius="var(--radius-md)" />
          <Skeleton height="240px" borderRadius="var(--radius-md)" className="mt-4" />
        </div>
      </div>
    );
  }

  if (error && items.length === 0) {
    return (
      <div className="screen-container approvals-screen" data-testid="screen-approvals">
        <EmptyState
          icon={<AlertTriangle size={36} className="text-danger" />}
          title="Failed to load approvals"
          description={error}
          actionLabel="Retry"
          onAction={fetchApprovals}
        />
      </div>
    );
  }

  return (
    <div className="screen-container approvals-screen" data-testid="screen-approvals">
      <div className="approvals-header-row">
        <div>
          <h2 className="screen-title">Human Supervisor Step-Up Review Queue</h2>
          <p className="screen-desc">
            Autonomous transactions exceeding instant threshold limits ($500.00) require human authorization cryptographically bound to the canonical RFC 8785 intent digest.
          </p>
        </div>
        <PillButton
          variant="secondary"
          size="sm"
          icon={<RefreshCw size={14} />}
          onClick={fetchApprovals}
        >
          Refresh Queue
        </PillButton>
      </div>

      {isAgentRole && (
        <div className="warning-banner mt-4" role="region" aria-label="Role Restriction Banner">
          <Shield size={16} className="warning-icon" />
          <span>
            <strong>Role Restriction:</strong> You are currently acting under the <code>AGENT</code> persona. Autonomous agents are strictly forbidden from authorizing their own transactions. Switch to <code>APPROVER</code> under More to authorize.
          </span>
        </div>
      )}

      {items.length > 0 ? (
        <div className="approvals-cards-list mt-4">
          {items.map((item) => (
            <ApprovalCard
              key={item.request_id}
              requestId={item.request_id}
              agentId={item.agent_id}
              recipientId={item.recipient_id}
              amountMinor={item.amount_minor}
              currency={item.currency}
              purpose={item.purpose}
              intentDigest={item.intent_digest}
              createdAtUtc={item.created_at_utc}
              isAgentRole={isAgentRole}
              isActionLoading={actionLoadingId === item.request_id}
              onApprove={(reqId, dig) => handleAction(reqId, dig, "ALLOW")}
              onDecline={(reqId, dig) => handleAction(reqId, dig, "DENY")}
            />
          ))}
        </div>
      ) : (
        <div className="mt-4">
          <EmptyState
            icon={<CheckCircle2 size={36} className="text-allow" />}
            title="Queue is completely clear"
            description="No transactions are currently awaiting supervisor authorization."
            actionLabel="Propose a New Transaction"
            onAction={() => onNavigate && onNavigate("pay")}
          />
        </div>
      )}
    </div>
  );
};
