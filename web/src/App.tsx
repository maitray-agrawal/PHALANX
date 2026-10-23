import React, { useState, useEffect, useCallback, useId } from "react";
import type { ColDef } from "ag-grid-community";
import { ModuleRegistry, AllCommunityModule } from "ag-grid-community";
import { AlertTriangle } from "lucide-react";
import {
  api,
  type AuthorizationResponse,
  type ExtractedIntent,
  type PendingStepUpItem,
  type LedgerEventItem,
  type MandateResponse,
  ApiError,
} from "./api";
import { PhalanxHeaderBrand } from "./components/PhalanxLogo";
import { ThemeSwitcher } from "./components/ThemeSwitcher";
import { CockpitOverview } from "./screens/CockpitOverview";
import { RequestConsole } from "./screens/RequestConsole";
import { ApprovalQueue } from "./screens/ApprovalQueue";
import { AuditLedger } from "./screens/AuditLedger";
import { MandateMeter } from "./screens/MandateMeter";
import { ReconciliationScreen } from "./screens/ReconciliationScreen";
import { SecurityCenter } from "./screens/SecurityCenter";
import { DeveloperConsole } from "./screens/DeveloperConsole";

ModuleRegistry.registerModules([AllCommunityModule]);

export type Role = "principal" | "agent" | "approver" | "auditor";
export type ActiveTab =
  | "overview"
  | "console"
  | "approvals"
  | "ledger"
  | "mandate"
  | "reconcile"
  | "security"
  | "developer";

interface ChatMessage {
  id: string;
  sender: "agent" | "system";
  text: string;
  timestamp: string;
  intent?: ExtractedIntent | null;
  heuristicFlagged?: boolean;
}

const INITIAL_MANDATE: MandateResponse = {
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
  allowed_payees: ["vendor-paypal-sandbox-1", "vendor-aws-cloud"],
  allowed_purposes: ["subscription", "hosting", "equipment", "renewal"],
  valid_from_utc: "2026-10-22T00:00:00Z",
  valid_until_utc: "2027-10-22T00:00:00Z",
  status: "ACTIVE",
  key_id: "key_7b4d91e0",
  signature:
    "ed25519:e4a9192fc88019b782c0bba9980d452093847291a84f3299c8201a88bbfe1009832716a504b2a",
};

const INITIAL_STEP_UPS: PendingStepUpItem[] = [
  {
    request_id: "req_stepup_1001",
    agent_id: "agent-auto-1",
    recipient_id: "vendor-paypal-sandbox-1",
    amount_minor: 120000,
    currency: "USD",
    purpose: "Equipment invoice review",
    intent_digest: "7a89f302b1c4e8590d9a62310188ef4a9b7e12f0a1d401ec8891000b0188992a",
    created_at_utc: "2026-10-22T12:05:14Z",
    status: "PENDING",
  },
];

const INITIAL_LEDGER: LedgerEventItem[] = [
  {
    event_id: "evt_000001_8a12f901",
    event_type: "AUTHORIZATION_EVALUATED",
    prev_hash: "0000000000000000000000000000000000000000000000000000000000000000",
    event_hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    payload: {
      agent_id: "agent-auto-1",
      recipient_id: "vendor-paypal-sandbox-1",
      amount_minor: 2500,
      currency: "USD",
      decision: "ALLOW",
      purpose: "Monthly subscription renewal",
      recorded_at_utc: "2026-10-22T12:00:00Z",
    },
  },
  {
    event_id: "evt_000002_4b98cf12",
    event_type: "AUTHORIZATION_EVALUATED",
    prev_hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    event_hash: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    payload: {
      agent_id: "agent-auto-1",
      recipient_id: "vendor-paypal-sandbox-1",
      amount_minor: 100000,
      currency: "USD",
      decision: "STEP_UP",
      purpose: "Equipment invoice review",
      recorded_at_utc: "2026-10-22T12:05:14Z",
    },
  },
  {
    event_id: "evt_000003_1e77aa99",
    event_type: "AUTHORIZATION_EVALUATED",
    prev_hash: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    event_hash: "9a21b36d2c41808e01bb364402a11b81604a558e22c9842a59e19cc17a80ddf1",
    payload: {
      agent_id: "rogue-agent-99",
      recipient_id: "external-unknown-wallet",
      amount_minor: 9500000,
      currency: "USD",
      decision: "DENY",
      purpose: "Unauthorized bulk withdrawal attempt",
      recorded_at_utc: "2026-10-22T12:12:30Z",
    },
  },
];

export const App: React.FC = () => {
  const [role, setRole] = useState<Role>("principal");
  const [token, setToken] = useState<string>("");
  const [activeTab, setActiveTab] = useState<ActiveTab>("console");
  const [globalError, setGlobalError] = useState<string | null>(null);

  // Chat and Intent Console State
  const [chatInput, setChatInput] = useState<string>(
    "Pay $25.00 for monthly subscription renewal to vendor-paypal-sandbox-1"
  );
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      id: "msg_init_01",
      sender: "system",
      text: "PHALANX Autonomous Assistant active. Propose a financial payment intent below. Untrusted text is safely wrapped in delimiters before extraction.",
      timestamp: "12:00:00 UTC",
    },
  ]);
  const [isExtracting, setIsExtracting] = useState<boolean>(false);
  const [extractedIntent, setExtractedIntent] = useState<ExtractedIntent | null>({
    agent_id: "agent-auto-1",
    recipient_id: "vendor-paypal-sandbox-1",
    amount_minor: 2500,
    currency: "USD",
    purpose: "Monthly subscription renewal",
    idempotency_key: "intent_sub_001",
    anomaly_signal: null,
  });
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);
  const [latestDecision, setLatestDecision] = useState<AuthorizationResponse | null>(null);

  // Step-Up Approvals State
  const [stepUps, setStepUps] = useState<PendingStepUpItem[]>(INITIAL_STEP_UPS);
  const [isLoadingApprovals, setIsLoadingApprovals] = useState<boolean>(false);
  const [tamperedItemMap, setTamperedItemMap] = useState<Record<string, boolean>>({});
  const [approvingRequestId, setApprovingRequestId] = useState<string | null>(null);

  // Audit Ledger State
  const [ledgerEvents, setLedgerEvents] = useState<LedgerEventItem[]>(INITIAL_LEDGER);
  const [isLoadingLedger, setIsLoadingLedger] = useState<boolean>(false);
  const [isVerifyingChain, setIsVerifyingChain] = useState<boolean>(false);
  const [chainIntegrity, setChainIntegrity] = useState<{
    isValid: boolean;
    message: string;
    brokenIndex: number | null;
  }>({
    isValid: true,
    message: "Cryptographic chain verified (3/3 links intact)",
    brokenIndex: null,
  });

  // Mandate State
  const [mandate, setMandate] = useState<MandateResponse | null>(INITIAL_MANDATE);
  const [isLoadingMandate, setIsLoadingMandate] = useState<boolean>(false);

  // Reconciliation State (F6 Ambiguous Rail Lifecycle)
  const [reconcileItems, setReconcileItems] = useState<
    Array<{
      request_id: string;
      agent_id: string;
      amount_minor: number;
      currency: string;
      payout_id?: string | null;
      state: string;
    }>
  >([
    {
      request_id: "req_ambiguous_7701",
      agent_id: "agent-auto-1",
      amount_minor: 45000,
      currency: "USD",
      payout_id: "PAYOUT_NET_TIMEOUT_7701",
      state: "RECONCILE",
    },
  ]);
  const [reconcileFeedback, setReconcileFeedback] = useState<string | null>(null);

  const handleResolveReconcile = async (
    requestId: string,
    status: "SUCCESS" | "FAILED" | "UNKNOWN"
  ) => {
    try {
      const res = await api.resolveReconcile(requestId, status, token, role);
      setReconcileFeedback(`Transaction ${requestId} updated: state transitioned to ${res.state}`);
      setReconcileItems((prev) =>
        prev.map((item) =>
          item.request_id === requestId ? { ...item, state: res.state } : item
        )
      );
    } catch {
      const simulatedState =
        status === "SUCCESS" ? "SETTLED" : status === "FAILED" ? "FAILED" : "RECONCILE";
      setReconcileFeedback(`[Rail Simulator] ${requestId} transitioned to ${simulatedState}`);
      setReconcileItems((prev) =>
        prev.map((item) =>
          item.request_id === requestId ? { ...item, state: simulatedState } : item
        )
      );
    }
  };

  // Accessible Form IDs
  const chatInputId = useId();
  const agentFieldId = useId();
  const recipientFieldId = useId();
  const amountFieldId = useId();
  const purposeFieldId = useId();

  // Acquire role demo token
  const refreshRoleToken = useCallback(async (newRole: Role) => {
    try {
      const res = await api.getDemoToken(newRole, "demo-principal", "agent-auto-1");
      setToken(res.access_token);
    } catch {
      // Fallback in test environment or offline
      setToken(`demo-token-${newRole}`);
    }
  }, []);

  useEffect(() => {
    refreshRoleToken(role);
  }, [role, refreshRoleToken]);

  // Load approvals from real backend
  const loadApprovals = useCallback(async () => {
    setIsLoadingApprovals(true);
    setGlobalError(null);
    try {
      const items = await api.getPendingApprovals(token, role);
      setStepUps(items);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setStepUps([]);
      } else {
        setGlobalError(err instanceof Error ? err.message : "Failed to load approval queue");
      }
    } finally {
      setIsLoadingApprovals(false);
    }
  }, [token, role]);

  // Load ledger from real backend
  const loadLedger = useCallback(async () => {
    setIsLoadingLedger(true);
    setGlobalError(null);
    try {
      const events = await api.getLedgerEvents(token, role);
      setLedgerEvents(events);
      const verifyRes = await api.verifyLedger(token, role);
      setChainIntegrity({
        isValid: verifyRes.is_valid,
        message: verifyRes.message,
        brokenIndex: verifyRes.broken_index,
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        // Agent lacks permission to browse ledger
      } else {
        setGlobalError(err instanceof Error ? err.message : "Failed to load ledger events");
      }
    } finally {
      setIsLoadingLedger(false);
    }
  }, [token, role]);

  // Load mandate from real backend
  const loadMandate = useCallback(async () => {
    setIsLoadingMandate(true);
    setGlobalError(null);
    try {
      const m = await api.getMandate("mandate_default_sandbox", token, role);
      setMandate(m);
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : "Failed to load active mandate");
    } finally {
      setIsLoadingMandate(false);
    }
  }, [token, role]);

  // Load view data on tab change
  useEffect(() => {
    if (activeTab === "approvals") {
      loadApprovals();
    } else if (activeTab === "ledger") {
      loadLedger();
    } else if (activeTab === "mandate") {
      loadMandate();
    }
  }, [activeTab, loadApprovals, loadLedger, loadMandate]);

  // Handler: Natural language chat intent extraction
  const handleAssistantChat = async (promptText = chatInput) => {
    if (!promptText.trim()) return;
    setIsExtracting(true);
    setGlobalError(null);

    const newMsg: ChatMessage = {
      id: `msg_${Date.now()}`,
      sender: "agent",
      text: promptText,
      timestamp: new Date().toLocaleTimeString(),
    };
    setChatMessages((prev) => [...prev, newMsg]);

    try {
      const res = await api.assistantChat(promptText, "agent-auto-1", token, role);
      const replyMsg: ChatMessage = {
        id: `msg_sys_${Date.now()}`,
        sender: "system",
        text: res.reply,
        timestamp: new Date().toLocaleTimeString(),
        intent: res.intent,
        heuristicFlagged: res.heuristic_flagged,
      };
      setChatMessages((prev) => [...prev, replyMsg]);
      if (res.intent) {
        setExtractedIntent(res.intent);
      }
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : "Assistant extraction failed");
    } finally {
      setIsExtracting(false);
    }
  };

  const handlePresetSelect = (text: string) => {
    setChatInput(text);
    handleAssistantChat(text);
  };

  // Handler: Submit payment intent to policy core
  const handleEvaluateIntent = async () => {
    if (!extractedIntent) return;
    setIsEvaluating(true);
    setGlobalError(null);

    try {
      const cmd = {
        agent_id: extractedIntent.agent_id,
        recipient_id: extractedIntent.recipient_id,
        amount_minor: extractedIntent.amount_minor,
        currency: extractedIntent.currency,
        purpose: extractedIntent.purpose,
        idempotency_key: extractedIntent.idempotency_key || `key_${Date.now()}`,
        anomaly_signal: extractedIntent.anomaly_signal || null,
      };
      const res = await api.createPaymentRequest(cmd, token, role);
      setLatestDecision(res);

      if (res.decision === "STEP_UP") {
        loadApprovals();
      }
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : "Policy evaluation failed");
    } finally {
      setIsEvaluating(false);
    }
  };

  // Handler: Human supervisor approval decision
  const handleApprovalDecision = async (
    reqId: string,
    digest: string,
    decision: "ALLOW" | "DENY",
    reason: string
  ) => {
    if (role === "agent") {
      setGlobalError(
        "Security Violation: Autonomous agent role cannot authorize transactions (manual 18, 56.16)."
      );
      return;
    }

    setApprovingRequestId(reqId);
    setGlobalError(null);

    try {
      const isTampered = tamperedItemMap[reqId];
      const digestToSend = isTampered
        ? "0000000000000000000000000000000000000000000000000000000000000000"
        : digest;

      await api.submitApproval(
        reqId,
        digestToSend,
        decision,
        reason,
        token,
        role
      );

      await loadApprovals();
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : "Approval execution failed");
    } finally {
      setApprovingRequestId(null);
    }
  };

  const toggleTamper = (reqId: string) => {
    setTamperedItemMap((prev) => ({
      ...prev,
      [reqId]: !prev[reqId],
    }));
  };

  // Handler: Verify Ledger Chain
  const handleVerifyChain = async () => {
    setIsVerifyingChain(true);
    setGlobalError(null);
    try {
      const res = await api.verifyLedger(token, role);
      setChainIntegrity({
        isValid: res.is_valid,
        message: res.message,
        brokenIndex: res.broken_index,
      });
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : "Ledger verification failed");
    } finally {
      setIsVerifyingChain(false);
    }
  };

  // Handler: Simulate Database Tampering
  const handleTamperLedger = async () => {
    setGlobalError(null);
    try {
      await api.tamperLedger(token, role);
      await loadLedger();
    } catch {
      setChainIntegrity({
        isValid: false,
        message: "CRITICAL: Broken hash chain link at Block 2! Hash mismatch detected.",
        brokenIndex: 1,
      });
      setLedgerEvents((rows) =>
        rows.map((r, i) =>
          i === 1
            ? {
                ...r,
                payload: { ...r.payload, amount_minor: 99999999 },
              }
            : r
        )
      );
    }
  };

  // Handler: Restore True Ledger
  const handleRestoreLedger = async () => {
    setGlobalError(null);
    try {
      await api.restoreLedger(token, role);
      await loadLedger();
    } catch {
      setChainIntegrity({
        isValid: true,
        message: "Cryptographic chain verified (3/3 links intact)",
        brokenIndex: null,
      });
      setLedgerEvents(INITIAL_LEDGER);
    }
  };

  // AG Grid column definitions
  const ledgerColDefs: ColDef<LedgerEventItem>[] = [
    { field: "event_id", headerName: "Event ID", width: 170 },
    {
      field: "prev_hash",
      headerName: "Previous Hash",
      width: 140,
      valueFormatter: (p) => (p.value ? `${p.value.slice(0, 10)}...` : "GENESIS"),
    },
    {
      field: "event_hash",
      headerName: "Block Hash",
      width: 140,
      valueFormatter: (p) => (p.value ? `${p.value.slice(0, 10)}...` : ""),
    },
    {
      headerName: "Agent ID",
      width: 150,
      valueGetter: (p) => p.data?.payload?.agent_id || "system",
    },
    {
      headerName: "Recipient",
      width: 170,
      valueGetter: (p) => p.data?.payload?.recipient_id || "treasury",
    },
    {
      headerName: "Amount",
      width: 130,
      cellClass: "tabular-nums",
      valueGetter: (p) => {
        const minor = p.data?.payload?.amount_minor;
        return typeof minor === "number" ? `$${(minor / 100).toFixed(2)}` : "$0.00";
      },
    },
    {
      headerName: "Decision",
      width: 120,
      cellRenderer: (p: { data?: LedgerEventItem }) => {
        const val = p.data?.payload?.decision || "ALLOW";
        const cls =
          val === "ALLOW"
            ? "badge-allow"
            : val === "STEP_UP"
              ? "badge-step-up"
              : "badge-deny";
        return <span className={cls}>{val}</span>;
      },
    },
    {
      headerName: "Purpose & Invariants",
      flex: 1,
      valueGetter: (p) => p.data?.payload?.purpose || "Authorization ledger entry",
    },
  ];

  return (
    <div className="app-container">
      {/* Top Header & Role Switcher */}
      <header className="header" role="banner">
        <div className="brand">
          <PhalanxHeaderBrand size={42} showTagline={true} />
        </div>

        <div className="header-controls">
          <ThemeSwitcher />

          <div
            className="role-switcher"
            role="radiogroup"
            aria-label="Active Operator Role"
          >
            <span className="role-label" id="role-label">
              Active Persona:
            </span>
            {(["principal", "agent", "approver", "auditor"] as Role[]).map((r) => (
              <button
                key={r}
                type="button"
                role="radio"
                aria-checked={role === r}
                className={`role-btn ${role === r ? "active" : ""}`}
                onClick={() => setRole(r)}
              >
                {r.toUpperCase()}
              </button>
            ))}
          </div>

          <div className="status-badge" role="status" aria-label="System Security Status">
            <span className="pulse-dot" aria-hidden="true"></span>
            <span>PAYPAL SANDBOX GUARD ACTIVE</span>
          </div>
        </div>
      </header>

      {/* Global Error Banner (Problem+JSON display) */}
      {globalError && (
        <div className="error-banner" role="alert">
          <AlertTriangle className="error-icon" aria-hidden="true" />
          <span>{globalError}</span>
          <button
            type="button"
            className="dismiss-btn"
            onClick={() => setGlobalError(null)}
            aria-label="Dismiss Error"
          >
            ✕
          </button>
        </div>
      )}

      {/* Navigation Tabs */}
      <nav className="tab-nav" role="tablist" aria-label="Dashboard Scenes">
        <button
          type="button"
          role="tab"
          id="tab-overview"
          aria-selected={activeTab === "overview"}
          aria-controls="panel-overview"
          className={`tab-btn ${activeTab === "overview" ? "active" : ""}`}
          onClick={() => setActiveTab("overview")}
        >
          Overview
        </button>
        <button
          type="button"
          role="tab"
          id="tab-console"
          aria-selected={activeTab === "console"}
          aria-controls="panel-console"
          className={`tab-btn ${activeTab === "console" ? "active" : ""}`}
          onClick={() => setActiveTab("console")}
        >
          Scene 1: Request Console
        </button>
        <button
          type="button"
          role="tab"
          id="tab-approvals"
          aria-selected={activeTab === "approvals"}
          aria-controls="panel-approvals"
          className={`tab-btn ${activeTab === "approvals" ? "active" : ""}`}
          onClick={() => setActiveTab("approvals")}
        >
          Scene 2: Step-Up Approvals
          {stepUps.length > 0 && (
            <span className="tab-badge" aria-label={`${stepUps.length} pending items`}>
              {stepUps.length}
            </span>
          )}
        </button>
        <button
          type="button"
          role="tab"
          id="tab-ledger"
          aria-selected={activeTab === "ledger"}
          aria-controls="panel-ledger"
          className={`tab-btn ${activeTab === "ledger" ? "active" : ""}`}
          onClick={() => setActiveTab("ledger")}
        >
          Scene 3: Cryptographic Audit Ledger
        </button>
        <button
          type="button"
          role="tab"
          id="tab-mandate"
          aria-selected={activeTab === "mandate"}
          aria-controls="panel-mandate"
          className={`tab-btn ${activeTab === "mandate" ? "active" : ""}`}
          onClick={() => setActiveTab("mandate")}
        >
          Ed25519 Mandate
        </button>
        <button
          type="button"
          role="tab"
          id="tab-reconcile"
          aria-selected={activeTab === "reconcile"}
          aria-controls="panel-reconcile"
          className={`tab-btn ${activeTab === "reconcile" ? "active" : ""}`}
          onClick={() => setActiveTab("reconcile")}
        >
          Rail Reconciliation (F6)
          {reconcileItems.length > 0 && (
            <span className="tab-badge" aria-label={`${reconcileItems.length} held reservations`}>
              {reconcileItems.length}
            </span>
          )}
        </button>
        <button
          type="button"
          role="tab"
          id="tab-security"
          aria-selected={activeTab === "security"}
          aria-controls="panel-security"
          className={`tab-btn ${activeTab === "security" ? "active" : ""}`}
          onClick={() => setActiveTab("security")}
        >
          Security Center
        </button>
        <button
          type="button"
          role="tab"
          id="tab-developer"
          aria-selected={activeTab === "developer"}
          aria-controls="panel-developer"
          className={`tab-btn ${activeTab === "developer" ? "active" : ""}`}
          onClick={() => setActiveTab("developer")}
        >
          Developer & MCP
        </button>
      </nav>

      {/* Main Content Area */}
      <main className="main-content">
        {activeTab === "overview" && (
          <CockpitOverview
            stepUpsCount={stepUps.length}
            chainIntegrity={chainIntegrity}
            ledgerEventsCount={ledgerEvents.length}
            setActiveTab={setActiveTab}
            onNavigate={(tab) => setActiveTab(tab as ActiveTab)}
          />
        )}

        {activeTab === "console" && (
          <RequestConsole
            chatInput={chatInput}
            setChatInput={setChatInput}
            chatMessages={chatMessages}
            isExtracting={isExtracting}
            handleAssistantChat={handleAssistantChat}
            handlePresetSelect={handlePresetSelect}
            extractedIntent={extractedIntent}
            setExtractedIntent={setExtractedIntent}
            isEvaluating={isEvaluating}
            handleEvaluateIntent={handleEvaluateIntent}
            latestDecision={latestDecision}
            chatInputId={chatInputId}
            agentFieldId={agentFieldId}
            recipientFieldId={recipientFieldId}
            amountFieldId={amountFieldId}
            purposeFieldId={purposeFieldId}
          />
        )}

        {activeTab === "approvals" && (
          <ApprovalQueue
            role={role}
            stepUps={stepUps}
            isLoadingApprovals={isLoadingApprovals}
            loadApprovals={loadApprovals}
            tamperedItemMap={tamperedItemMap}
            toggleTamper={toggleTamper}
            approvingRequestId={approvingRequestId}
            handleApprovalDecision={handleApprovalDecision}
          />
        )}

        {activeTab === "ledger" && (
          <AuditLedger
            ledgerEvents={ledgerEvents}
            isLoadingLedger={isLoadingLedger}
            isVerifyingChain={isVerifyingChain}
            chainIntegrity={chainIntegrity}
            loadLedger={loadLedger}
            handleVerifyChain={handleVerifyChain}
            handleTamperLedger={handleTamperLedger}
            handleRestoreLedger={handleRestoreLedger}
            ledgerColDefs={ledgerColDefs}
          />
        )}

        {activeTab === "mandate" && (
          <MandateMeter mandate={mandate} isLoadingMandate={isLoadingMandate} />
        )}

        {activeTab === "reconcile" && (
          <ReconciliationScreen
            reconcileItems={reconcileItems}
            setReconcileItems={setReconcileItems}
            reconcileFeedback={reconcileFeedback}
            setReconcileFeedback={setReconcileFeedback}
            handleResolveReconcile={handleResolveReconcile}
          />
        )}

        {activeTab === "security" && <SecurityCenter />}

        {activeTab === "developer" && <DeveloperConsole />}
      </main>
    </div>
  );
};

export default App;
