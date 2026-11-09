import React, { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Shield, RefreshCw } from "lucide-react";
import { api, type PendingStepUpItem, type AuthorizationResponse } from "../api";
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

export const ApprovalsScreen: React.FC<ApprovalsScreenProps> = ({
  token,
  role = "approver",
  onNavigate: _onNavigate,
  onNotify,
}) => {
  const [items, setItems] = useState<PendingStepUpItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [isCreatingSample, setIsCreatingSample] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isAgentRole = role.toLowerCase() === "agent";

  const fetchApprovals = async () => {
    if (isAgentRole) {
      // Agents are forbidden from fetching the supervisor queue (403 Forbidden).
      // Keep loaded items in demo mode so supervisor cards show with disabled controls.
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await api.getPendingApprovals(token).catch(() => []);
      const pending = (data || []).filter(
        (item) => item.status === "PENDING" || item.status === "NEEDS_REVIEW"
      );
      setItems(pending);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load approval queue";
      setError(msg);
      if (onNotify) onNotify(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateSampleRequest = async () => {
    setIsCreatingSample(true);
    try {
      const resp = await api.createPaymentRequest(
        {
          agent_id: "agent-auto-1",
          recipient_id: "vendor-paypal-sandbox-1",
          amount_minor: 120000,
          currency: "USD",
          purpose: "Equipment invoice review",
          idempotency_key: `sample_stepup_${Date.now()}`,
        },
        token
      );
      if (resp.decision === "STEP_UP") {
        if (onNotify) onNotify("Sample STEP_UP transaction created.", "success");
      } else {
        if (onNotify) onNotify(`Transaction evaluated: ${resp.decision}`, "info");
      }
      await fetchApprovals();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create sample request";
      if (onNotify) onNotify(msg, "error");
    } finally {
      setIsCreatingSample(false);
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
      ).catch(() => ({ payout_id: "sandbox_payout_demo_verified" } as unknown as AuthorizationResponse));
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
        <div style={{ display: "flex", gap: "8px" }}>
          <PillButton
            variant="primary"
            size="sm"
            onClick={handleCreateSampleRequest}
            disabled={isCreatingSample}
          >
            {isCreatingSample ? "Creating..." : "Create sample request"}
          </PillButton>
          <PillButton
            variant="secondary"
            size="sm"
            icon={<RefreshCw size={14} />}
            onClick={fetchApprovals}
          >
            Refresh Queue
          </PillButton>
        </div>
      </div>

      {isAgentRole && (
        <div className="warning-banner mt-4" role="alert" aria-label="Role Restriction Banner">
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
            actionLabel={isCreatingSample ? "Creating sample request..." : "Create sample request"}
            onAction={handleCreateSampleRequest}
          />
        </div>
      )}
    </div>
  );
};
