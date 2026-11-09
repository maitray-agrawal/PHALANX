import React, { useEffect, useState } from "react";
import { RefreshCw, AlertTriangle } from "lucide-react";
import { api, type MandateResponse } from "../api";
import { MandateMeter } from "../components/MandateMeter";
import { PillButton } from "../components/PillButton";
import { EmptyState } from "../components/EmptyState";

export interface MandatesScreenProps {
  token?: string;
  onNavigate?: (tab: string, receiptId?: string) => void;
  onNotify?: (msg: string, type: "success" | "error" | "info") => void;
}

const DEFAULT_MANDATE: MandateResponse = {
  mandate_id: "mandate_default_sandbox",
  version: 1,
  principal_id: "principal_treasury",
  agent_id: "agent-auto-1",
  single_limit_minor: 500000,
  instant_threshold_minor: 50000,
  lifetime_budget_minor: 2500000,
  spent_budget_minor: 0,
  remaining_budget_minor: 2500000,
  currency: "USD",
  allowed_payees: ["vendor-paypal-sandbox-1", "office_supplies_inc", "cloud_compute_corp"],
  allowed_purposes: ["SaaS Subscriptions", "Cloud Hosting Infrastructure", "Operational Procurement"],
  valid_from_utc: "2026-11-01T00:00:00Z",
  valid_until_utc: "2027-03-31T23:59:59Z",
  status: "ACTIVE",
  key_id: "ed25519-phalanx-core-2026",
  signature: "d8e3b2...c4a1 (Cryptographically verified)",
};

export const MandatesScreen: React.FC<MandatesScreenProps> = ({
  token,
  onNotify,
}) => {
  const [mandate, setMandate] = useState<MandateResponse>(DEFAULT_MANDATE);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMandate = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getMandate("mandate_default_sandbox", token);
      setMandate(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load active mandate";
      setError(msg);
      if (onNotify) onNotify(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMandate();
  }, [token]);

  return (
    <div className="screen-container mandates-screen" data-testid="screen-mandates">
      <div className="mandates-header-row">
        <div>
          <h2 className="screen-title">Ed25519 Authority Mandate</h2>
          <p className="screen-desc">
            Autonomous agent financial authority is strictly bounded by cryptographic parameters signed with the Principal's private key.
          </p>
        </div>
        <PillButton
          variant="secondary"
          size="sm"
          icon={<RefreshCw size={14} />}
          onClick={fetchMandate}
        >
          Refresh Mandate
        </PillButton>
      </div>

      <div className="mt-4">
        {error && !mandate ? (
          <EmptyState
            icon={<AlertTriangle size={36} className="text-danger" />}
            title="Failed to load mandate parameters"
            description={error}
            actionLabel="Retry"
            onAction={fetchMandate}
          />
        ) : (
          <MandateMeter mandate={mandate} isLoading={loading} />
        )}
      </div>
    </div>
  );
};
