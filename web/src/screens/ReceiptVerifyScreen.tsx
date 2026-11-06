import React, { useEffect, useState } from "react";
import {
  FileText,
  ShieldCheck,
  ShieldAlert,
  ArrowLeft,
  Search,
} from "lucide-react";
import {
  api,
  type ReceiptResponse,
  type ReceiptVerificationResponse,
} from "../api";
import { ReceiptCard } from "../components/ReceiptCard";
import { PillButton } from "../components/PillButton";
import { Skeleton } from "../components/Skeleton";
import { EmptyState } from "../components/EmptyState";

export interface ReceiptVerifyScreenProps {
  receiptId?: string | null;
  token?: string;
  onBack?: () => void;
  onNotify?: (msg: string, type: "success" | "error" | "info") => void;
}

export const ReceiptVerifyScreen: React.FC<ReceiptVerifyScreenProps> = ({
  receiptId,
  token,
  onBack,
  onNotify,
}) => {
  const [_activeReceiptId, setActiveReceiptId] = useState(receiptId || "");
  const [inputReceiptId, setInputReceiptId] = useState(receiptId || "");
  const [receipt, setReceipt] = useState<ReceiptResponse | null>(null);
  const [verifyResult, setVerifyResult] = useState<ReceiptVerificationResponse | null>(null);

  const [isLoading, setIsLoading] = useState(false);
  const [_isVerifying, setIsVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadReceiptAndVerify = async (id: string) => {
    if (!id.trim()) return;
    setIsLoading(true);
    setError(null);
    try {
      // 1. Fetch full receipt details
      const rcpt = await api.getReceipt(id, token).catch(() => null);
      setReceipt(rcpt);

      // 2. Run public verification recomputing the block hash and continuity
      const pubVer = await api.verifyReceipt(id).catch(() => null);
      setVerifyResult(pubVer);

      if (!rcpt && !pubVer) {
        throw new Error(`Receipt '${id}' not found in cryptographic ledger.`);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load receipt";
      setError(msg);
      if (onNotify) onNotify(msg, "error");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (receiptId) {
      setActiveReceiptId(receiptId);
      setInputReceiptId(receiptId);
      loadReceiptAndVerify(receiptId);
    }
  }, [receiptId]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputReceiptId.trim()) return;
    setActiveReceiptId(inputReceiptId.trim());
    loadReceiptAndVerify(inputReceiptId.trim());
  };

  const handleVerify = async (id: string) => {
    setIsVerifying(true);
    try {
      const ver = await api.verifyReceipt(id);
      setVerifyResult(ver);
      if (onNotify) {
        onNotify(
          ver.is_valid
            ? `Receipt proof verified: valid block in verified chain`
            : `Proof failed: Broken block #${ver.broken_block}`,
          ver.is_valid ? "success" : "error"
        );
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Verification failed";
      if (onNotify) onNotify(msg, "error");
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div className="screen-container receipt-screen" data-testid="screen-receipt">
      <div className="receipt-page-header">
        <div className="header-nav-row">
          {onBack && (
            <button type="button" className="back-link-btn" onClick={onBack}>
              <ArrowLeft size={16} className="inline-icon" /> Back to Activity
            </button>
          )}
          <h2 className="screen-title">Cryptographic Receipt & Proof Verifier</h2>
        </div>
        <p className="screen-desc">
          Public read-only verification recomputes SHA-256 canonical payload digests and hash chain continuity from genesis to block tail.
        </p>

        {/* Receipt ID Search Bar */}
        <form className="receipt-search-form mt-4" onSubmit={handleSearchSubmit}>
          <div className="search-input-wrap">
            <Search size={16} className="search-icon" aria-hidden="true" />
            <input
              type="text"
              className="search-input mono"
              placeholder="Enter receipt ID (e.g. rcpt_evt_000001_8a12f901)"
              value={inputReceiptId}
              onChange={(e) => setInputReceiptId(e.target.value)}
            />
          </div>
          <PillButton type="submit" variant="primary" size="md">
            Verify Proof
          </PillButton>
        </form>
      </div>

      {isLoading && (
        <div className="mt-4">
          <Skeleton height="360px" borderRadius="var(--radius-md)" />
        </div>
      )}

      {error && !isLoading && (
        <div className="mt-4">
          <EmptyState
            icon={<ShieldAlert size={36} className="text-danger" />}
            title="Receipt Not Found"
            description={error}
            actionLabel="Return to Activity Feed"
            onAction={onBack}
          />
        </div>
      )}

      {!isLoading && !error && receipt && (
        <div className="receipt-content mt-4">
          {/* Public Verification Banner */}
          {verifyResult && (
            <div
              className={`public-verify-banner ${verifyResult.is_valid ? "pass" : "fail"}`}
              role="status"
              aria-live="polite"
            >
              <div className="verify-badge-icon">
                {verifyResult.is_valid ? (
                  <ShieldCheck size={28} className="text-allow" />
                ) : (
                  <ShieldAlert size={28} className="text-danger" />
                )}
              </div>
              <div className="verify-details">
                <div className="verify-status-title">
                  Verification Outcome: <strong>{verifyResult.status}</strong>
                </div>
                <p className="verify-msg">{verifyResult.message}</p>
                <div className="verify-meta mono">
                  <span>Block Sequence: #{verifyResult.ledger_sequence}</span> •{" "}
                  <span>Event Hash: {verifyResult.event_hash.slice(0, 16)}...</span>
                </div>
              </div>
            </div>
          )}

          <ReceiptCard
            receipt={receipt}
            onVerify={handleVerify}
            className="mt-4"
          />
        </div>
      )}

      {!isLoading && !error && !receipt && verifyResult && (
        <div className="public-only-view card mt-4">
          <div className={`public-verify-banner ${verifyResult.is_valid ? "pass" : "fail"}`}>
            <ShieldCheck size={28} className="text-allow" />
            <div>
              <h3 className="verify-status-title">
                Public Ledger Verification: {verifyResult.status}
              </h3>
              <p className="verify-msg">{verifyResult.message}</p>
            </div>
          </div>
        </div>
      )}

      {!isLoading && !error && !receipt && !verifyResult && (
        <div className="mt-4">
          <EmptyState
            icon={<FileText size={36} />}
            title="Search for a Transaction Receipt"
            description="Enter a receipt ID or transaction hash above to inspect cryptographic hash chain proofs."
          />
        </div>
      )}
    </div>
  );
};
