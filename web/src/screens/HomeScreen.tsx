import React, { useEffect, useState } from "react";
import { AlertTriangle, Send } from "lucide-react";
import { api, type OverviewResponse, type ActivityItem } from "../api";
import { PillButton } from "../components/PillButton";
import { ActivityRow } from "../components/ActivityRow";
import { Skeleton } from "../components/Skeleton";
import { EmptyState } from "../components/EmptyState";

export interface HomeScreenProps {
  token?: string;
  onNavigate: (tab: string, receiptId?: string) => void;
  onNotify?: (msg: string, type: "success" | "error" | "info") => void;
}

const DEFAULT_OVERVIEW: OverviewResponse = {
  remaining_authority: 2475000,
  pending_approval_count: 0,
  last_activity: "2026-10-22T12:05:00Z",
};

export const HomeScreen: React.FC<HomeScreenProps> = ({
  token,
  onNavigate,
  onNotify,
}) => {
  const [overview, setOverview] = useState<OverviewResponse>(DEFAULT_OVERVIEW);
  const [recentActivity, setRecentActivity] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchHomeData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [ovData, actData] = await Promise.all([
        api.getOverview(token).catch(() => ({
          remaining_authority: 2475000,
          pending_approval_count: 0,
          last_activity: null,
        })),
        api.getActivity(undefined, 5, token).catch(() => ({
          items: [],
          next_cursor: null,
          has_more: false,
        })),
      ]);
      setOverview(ovData);
      setRecentActivity(actData.items);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load dashboard overview";
      setError(msg);
      if (onNotify) onNotify(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHomeData();
  }, [token]);

  const formatMoney = (minor: number) =>
    (minor / 100).toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
    });

  if (loading && !overview) {
    return (
      <div className="screen-container home-screen">
        <div className="home-stats-grid">
          <Skeleton height="110px" borderRadius="var(--radius-md)" />
          <Skeleton height="110px" borderRadius="var(--radius-md)" />
          <Skeleton height="110px" borderRadius="var(--radius-md)" />
        </div>
        <div className="home-action-banner card mt-4">
          <Skeleton height="80px" borderRadius="var(--radius-md)" />
        </div>
        <div className="home-activity-section mt-4">
          <Skeleton height="200px" borderRadius="var(--radius-md)" />
        </div>
      </div>
    );
  }

  if (error && !overview) {
    return (
      <div className="screen-container home-screen">
        <EmptyState
          icon={<AlertTriangle size={36} className="text-danger" />}
          title="Unable to load overview"
          description={error}
          actionLabel="Retry"
          onAction={fetchHomeData}
        />
      </div>
    );
  }

  const remaining = overview ? overview.remaining_authority : 2475000;
  const pendingCount = overview ? overview.pending_approval_count : 0;
  const lastActivity = overview && overview.last_activity ? overview.last_activity : "No activity recorded";

  return (
    <div className="screen-container home-screen" data-testid="screen-home">
      {/* Three Numbers Header */}
      <section className="home-stats-grid" aria-label="Operational Metrics">
        <div className="stat-card card">
          <span className="stat-label">REMAINING AUTHORITY</span>
          <div className="stat-value text-primary tabular-nums">
            {formatMoney(remaining)}
          </div>
          <span className="stat-subtext">Active Ed25519 Mandate Cap</span>
        </div>

        <div className="stat-card card">
          <span className="stat-label">PENDING APPROVALS</span>
          <div className={`stat-value tabular-nums ${pendingCount > 0 ? "text-stepup" : "text-primary"}`}>
            {pendingCount}
          </div>
          <span className="stat-subtext">
            {pendingCount > 0 ? "Requires human supervisor review" : "No pending step-ups"}
          </span>
        </div>

        <div className="stat-card card">
          <span className="stat-label">LAST RECORDED ACTIVITY</span>
          <div className="stat-value stat-time mono">
            {lastActivity.length > 20 ? lastActivity.slice(11, 19) + " UTC" : lastActivity}
          </div>
          <span className="stat-subtext">Cryptographic ledger stream</span>
        </div>
      </section>

      {/* One Sticky/Prominent Primary Action */}
      <section className="home-action-banner card">
        <div className="banner-content">
          <div>
            <h2 className="banner-title">Authorize Autonomous Payment</h2>
            <p className="banner-desc">
              Submit proposed transactions through the pure policy engine with instant limits and human-in-the-loop governance.
            </p>
          </div>
          <PillButton
            variant="primary"
            size="lg"
            icon={<Send size={18} />}
            onClick={() => onNavigate("pay")}
          >
            Pay & Request
          </PillButton>
        </div>
      </section>

      {/* Recent Activity List */}
      <section className="home-activity-section card">
        <div className="section-header-row">
          <div>
            <h3 className="section-title">Recent Activity</h3>
            <p className="section-subtitle">Real-time ledger entries evaluated by policy rules.</p>
          </div>
          <PillButton
            variant="ghost"
            size="sm"
            onClick={() => onNavigate("activity")}
          >
            View All Activity →
          </PillButton>
        </div>

        {recentActivity.length > 0 ? (
          <div className="activity-list">
            {recentActivity.map((item) => (
              <ActivityRow
                key={item.receipt_id}
                receiptId={item.receipt_id}
                decision={item.decision}
                amountMinor={item.amount}
                payee={item.payee}
                reasonCode={item.reason_code}
                providerState={item.provider_state}
                timestampUtc={item.timestamp_utc}
                onViewReceipt={(rcptId) => onNavigate("receipt", rcptId)}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            title="No transactions yet"
            description="Your autonomous agent has not initiated any financial transactions."
            actionLabel="Dispatch Payment"
            onAction={() => onNavigate("pay")}
          />
        )}
      </section>
    </div>
  );
};
