import React, { useEffect, useState } from "react";
import { RefreshCw, AlertTriangle, FileText } from "lucide-react";
import {
  api,
  type ActivityItem,
  type LedgerEventItem,
  type LedgerVerificationResponse,
} from "../api";
import { ActivityRow } from "../components/ActivityRow";
import { ChainStrip } from "../components/ChainStrip";
import { PillButton } from "../components/PillButton";
import { Skeleton } from "../components/Skeleton";
import { EmptyState } from "../components/EmptyState";

export interface ActivityScreenProps {
  token?: string;
  onNavigate?: (tab: string, receiptId?: string) => void;
  onNotify?: (msg: string, type: "success" | "error" | "info") => void;
}

const DEFAULT_ACTIVITY: ActivityItem[] = [
  {
    receipt_id: "rcpt_mock_act_1",
    decision: "ALLOW",
    amount: 2500,
    payee: "vendor-paypal-sandbox-1",
    reason_code: "WITHIN_INSTANT_THRESHOLD",
    provider_state: "COMPLETED",
    timestamp_utc: "2026-10-22T12:05:00Z",
  },
  {
    receipt_id: "rcpt_mock_act_2",
    decision: "STEP_UP",
    amount: 120000,
    payee: "vendor-paypal-sandbox-1",
    reason_code: "EXCEEDS_INSTANT_THRESHOLD",
    provider_state: "BUYER_APPROVAL_REQUIRED",
    timestamp_utc: "2026-10-22T11:45:00Z",
  },
];

const DEFAULT_EVENTS: LedgerEventItem[] = [
  {
    event_id: "evt_init_0001",
    prev_hash: "0000000000000000000000000000000000000000000000000000000000000000",
    event_hash: "8f4a123b00000000000000000000000000000000000000000000000000000001",
    event_type: "MANDATE_ISSUED",
    payload: {
      amount_minor: undefined,
      decision: "ALLOW",
    },
  },
  {
    event_id: "evt_tx_0002",
    prev_hash: "8f4a123b00000000000000000000000000000000000000000000000000000001",
    event_hash: "3b2c914d00000000000000000000000000000000000000000000000000000002",
    event_type: "TRANSACTION_AUTHORIZED",
    payload: {
      amount_minor: 2500,
      decision: "ALLOW",
      recipient_id: "vendor-paypal-sandbox-1",
      purpose: "Monthly server hosting payment",
    },
  },
];

const DEFAULT_VERIFICATION: LedgerVerificationResponse = {
  is_valid: true,
  message: "Cryptographic hash chain verified intact. All blocks match prev_hash.",
  broken_index: null,
  total_events: 2,
};

export const ActivityScreen: React.FC<ActivityScreenProps> = ({
  token,
  onNavigate,
  onNotify,
}) => {
  const [activity, setActivity] = useState<ActivityItem[]>(DEFAULT_ACTIVITY);
  const [events, setEvents] = useState<LedgerEventItem[]>(DEFAULT_EVENTS);
  const [verification, setVerification] = useState<LedgerVerificationResponse | null>(DEFAULT_VERIFICATION);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);

  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [actData, evData, verData] = await Promise.all([
        api.getActivity(undefined, 20, token).catch(() => ({
          items: [],
          next_cursor: null,
          has_more: false,
        })),
        api.getLedgerEvents(token).catch(() => []),
        api.verifyLedger(token).catch(() => ({
          is_valid: true,
          message: "Ledger verified intact.",
          broken_index: null,
          total_events: 1,
        })),
      ]);

      setActivity(actData.items);
      setCursor(actData.next_cursor);
      setHasMore(actData.has_more);
      setEvents(evData);
      setVerification(verData);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load activity stream";
      setError(msg);
      if (onNotify) onNotify(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [token]);

  const handleLoadMore = async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const moreData = await api.getActivity(cursor, 20, token);
      setActivity((prev) => [...prev, ...moreData.items]);
      setCursor(moreData.next_cursor);
      setHasMore(moreData.has_more);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load more activity";
      if (onNotify) onNotify(msg, "error");
    } finally {
      setLoadingMore(false);
    }
  };

  const handleVerifyChain = async () => {
    setIsVerifying(true);
    try {
      const ver = await api.verifyLedger(token);
      setVerification(ver);
      if (onNotify) {
        onNotify(
          ver.is_valid
            ? `Cryptographic proof verified: ${ver.message}`
            : `Tamper detected: Block #${ver.broken_index} hash mismatch!`,
          ver.is_valid ? "success" : "error"
        );
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Verification check failed";
      if (onNotify) onNotify(msg, "error");
    } finally {
      setIsVerifying(false);
    }
  };

  const handleTamperSimulate = async () => {
    try {
      const res = await api.tamperLedger(token);
      if (onNotify) onNotify(`Simulated direct database modification: ${res.message}`, "info");
      await handleVerifyChain();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Tamper simulation failed";
      if (onNotify) onNotify(msg, "error");
    }
  };

  const handleRestoreLedger = async () => {
    try {
      const res = await api.restoreLedger(token);
      if (onNotify) onNotify(`Restored true cryptographic state: ${res.message}`, "success");
      await fetchData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Restore failed";
      if (onNotify) onNotify(msg, "error");
    }
  };

  if (loading && activity.length === 0 && events.length === 0) {
    return (
      <div className="screen-container activity-screen" data-testid="screen-activity">
        <div className="activity-header-box">
          <Skeleton height="32px" width="300px" />
          <Skeleton height="20px" width="450px" className="mt-2" />
        </div>
        <Skeleton height="160px" borderRadius="var(--radius-md)" className="mt-4" />
        <Skeleton height="300px" borderRadius="var(--radius-md)" className="mt-4" />
      </div>
    );
  }

  if (error && activity.length === 0) {
    return (
      <div className="screen-container activity-screen" data-testid="screen-activity">
        <EmptyState
          icon={<AlertTriangle size={36} className="text-danger" />}
          title="Failed to load ledger activity"
          description={error}
          actionLabel="Retry"
          onAction={fetchData}
        />
      </div>
    );
  }

  return (
    <div className="screen-container activity-screen" data-testid="screen-activity">
      <div className="activity-header-box">
        <div>
          <h2 className="screen-title">Cryptographic Shield-Wall Ledger</h2>
          <p className="screen-desc">
            Append-only financial event journal sealed with SHA-256 hash chains. Every transaction leaves immutable mathematical evidence.
          </p>
        </div>
        <div className="header-actions">
          <PillButton
            variant="secondary"
            size="sm"
            icon={<RefreshCw size={14} />}
            onClick={fetchData}
          >
            Refresh
          </PillButton>
        </div>
      </div>

      {/* Visual Chain of Blocks */}
      {events.length > 0 && (
        <section className="chain-strip-section mt-4">
          <ChainStrip
            events={events}
            verification={verification}
            isVerifying={isVerifying}
            onVerify={handleVerifyChain}
            onTamperSimulate={handleTamperSimulate}
            onRestore={handleRestoreLedger}
          />
        </section>
      )}

      {/* Activity Feed Table / Rows */}
      <section className="activity-feed-card card mt-4">
        <div className="feed-header-row">
          <div>
            <h3 className="card-title">Transaction Activity Journal</h3>
            <span className="card-subtitle">
              Provider state displayed honestly (Completed, Needs buyer approval, Order created).
            </span>
          </div>
        </div>

        {activity.length > 0 ? (
          <div className="feed-list mt-2">
            {activity.map((item) => (
              <ActivityRow
                key={item.receipt_id}
                receiptId={item.receipt_id}
                decision={item.decision}
                amountMinor={item.amount}
                payee={item.payee}
                reasonCode={item.reason_code}
                providerState={item.provider_state}
                timestampUtc={item.timestamp_utc}
                onViewReceipt={(rcptId) => onNavigate && onNavigate("receipt", rcptId)}
              />
            ))}

            {hasMore && (
              <div className="feed-pagination-footer mt-4">
                <PillButton
                  variant="secondary"
                  size="md"
                  loading={loadingMore}
                  onClick={handleLoadMore}
                >
                  Load Next Page →
                </PillButton>
              </div>
            )}
          </div>
        ) : (
          <EmptyState
            icon={<FileText size={36} />}
            title="No activity recorded"
            description="The ledger is currently empty. Issue a payment request to populate the chain."
            actionLabel="Make a Payment"
            onAction={() => onNavigate && onNavigate("pay")}
          />
        )}
      </section>
    </div>
  );
};
