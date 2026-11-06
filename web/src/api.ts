/**
 * PHALANX Real Backend API Client.
 *
 * Invariants (manual 56.41):
 * - The UI communicates strictly with real application backend endpoints; no mocks in production code.
 * - Handles RFC 7807 Problem+JSON error envelopes.
 * - Supports authenticated role tokens (Bearer) and demo mode credentials.
 */

export interface DemoTokenResponse {
  access_token: string;
  token_type: string;
  role: string;
  expires_in_seconds: number;
}

export interface OverviewResponse {
  remaining_authority: number;
  pending_approval_count: number;
  last_activity: string | null;
}

export interface ActivityItem {
  receipt_id: string;
  decision: "ALLOW" | "STEP_UP" | "DENY";
  amount: number;
  payee: string;
  reason_code: string;
  provider_state: string;
  timestamp_utc: string;
}

export interface PaginatedActivityResponse {
  items: ActivityItem[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface HashChainProof {
  event_id: string;
  event_seq: number;
  prev_hash: string;
  event_hash: string;
  canonical_payload_hash: string;
  is_valid: boolean;
}

export interface ReceiptResponse {
  receipt_id: string;
  intent_digest: string;
  mandate_id: string;
  mandate_version: number;
  decision: "ALLOW" | "STEP_UP" | "DENY";
  reason_codes: string[];
  ledger_sequence: number;
  hash_chain_proof: HashChainProof;
  amount_minor: number;
  currency: string;
  payee: string;
  created_at_utc: string;
}

export interface ReceiptVerificationResponse {
  status: "PASS" | "FAIL";
  is_valid: boolean;
  receipt_id: string;
  decision: string;
  ledger_sequence: number;
  event_hash: string;
  broken_block: number | null;
  message: string;
}

export interface AttackLabItem {
  attack_name: string;
  target: string;
  blocked: boolean;
  decision: string;
  reason_code: string;
  description: string;
  reached_paypal: boolean;
}

export interface AttackLabResponse {
  attacks_run: number;
  all_defended: boolean;
  results: AttackLabItem[];
}

export interface ExtractedIntent {
  agent_id: string;
  recipient_id: string;
  amount_minor: number;
  currency: string;
  purpose: string;
  idempotency_key: string;
  anomaly_signal?: string | null;
}

export interface AssistantChatResponse {
  reply: string;
  intent: ExtractedIntent | null;
  heuristic_flagged: boolean;
  heuristic_reason: string | null;
}

export interface AuthorizationResponse {
  request_id: string;
  decision: "ALLOW" | "STEP_UP" | "DENY";
  reasons: string[];
  reason_codes: string[];
  escalated: boolean;
  event_id: string;
  intent_digest: string;
  evaluated_at_utc: string;
  payout_id?: string | null;
}

export interface AuthorizeTransactionCommand {
  agent_id: string;
  recipient_id: string;
  amount_minor: number;
  currency: string;
  purpose: string;
  idempotency_key: string;
  anomaly_signal?: string | null;
  invoice_reference?: string | null;
}

export interface PendingStepUpItem {
  request_id: string;
  agent_id: string;
  recipient_id: string;
  amount_minor: number;
  currency: string;
  purpose: string;
  intent_digest: string;
  created_at_utc: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
}

export interface LedgerEventItem {
  event_id: string;
  event_type: string;
  prev_hash: string;
  event_hash: string;
  payload: {
    agent_id?: string;
    recipient_id?: string;
    amount_minor?: number;
    currency?: string;
    purpose?: string;
    decision?: "ALLOW" | "STEP_UP" | "DENY";
    recorded_at_utc?: string;
    reasons?: string[];
    [key: string]: unknown;
  };
}

export interface LedgerVerificationResponse {
  is_valid: boolean;
  message: string;
  broken_index: number | null;
  total_events: number;
}

export interface MandateResponse {
  mandate_id: string;
  version: number;
  principal_id: string;
  agent_id: string;
  single_limit_minor: number;
  instant_threshold_minor: number;
  lifetime_budget_minor: number;
  spent_budget_minor: number;
  remaining_budget_minor: number;
  currency: string;
  allowed_payees: string[];
  allowed_purposes: string[];
  valid_from_utc: string;
  valid_until_utc: string;
  status: string;
  key_id: string;
  signature: string;
}

export class ApiError extends Error {
  public status: number;
  public detail: string;
  public title?: string;

  constructor(status: number, detail: string, title?: string) {
    super(detail || `API error ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.title = title;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string
): Promise<T> {
  const headers = new Headers(options.headers || {});
  headers.set("Content-Type", "application/json");

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(path, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}: ${res.statusText}`;
    let title: string | undefined;
    try {
      const errJson = await res.json();
      detail = errJson.detail || errJson.message || detail;
      title = errJson.title;
    } catch {
      // Non-JSON response
    }
    throw new ApiError(res.status, detail, title);
  }

  return res.json() as Promise<T>;
}

export const api = {
  getDemoToken: (role: string, principalId = "principal_treasury", agentId?: string) =>
    request<DemoTokenResponse>("/v1/auth/demo-token", {
      method: "POST",
      body: JSON.stringify({ role, principal_id: principalId, agent_id: agentId }),
    }),

  getOverview: (token?: string) =>
    request<OverviewResponse>("/v1/overview", { method: "GET" }, token),

  getActivity: (cursor?: string, limit = 20, token?: string) => {
    const params = new URLSearchParams();
    if (cursor) params.set("cursor", cursor);
    if (limit) params.set("limit", limit.toString());
    const query = params.toString() ? `?${params.toString()}` : "";
    return request<PaginatedActivityResponse>(`/v1/activity${query}`, { method: "GET" }, token);
  },

  getReceipt: (receiptId: string, token?: string) =>
    request<ReceiptResponse>(`/v1/receipts/${receiptId}`, { method: "GET" }, token),

  verifyReceipt: (receiptId: string) =>
    request<ReceiptVerificationResponse>(`/v1/receipts/${receiptId}/verify`, { method: "GET" }),

  runAttackLab: (token?: string) =>
    request<AttackLabResponse>("/v1/attack-lab/run", { method: "POST" }, token),

  assistantChat: (message: string, agentId = "agent-auto-1", token?: string) =>
    request<AssistantChatResponse>(
      "/v1/assistant/chat",
      {
        method: "POST",
        body: JSON.stringify({ message, agent_id: agentId, session_id: "phalanx-session" }),
      },
      token
    ),

  createPaymentRequest: (cmd: AuthorizeTransactionCommand, token?: string) =>
    request<AuthorizationResponse>(
      "/v1/payment-requests",
      {
        method: "POST",
        body: JSON.stringify(cmd),
      },
      token
    ),

  getPendingApprovals: (token?: string) =>
    request<PendingStepUpItem[]>("/v1/approvals", { method: "GET" }, token),

  submitApproval: (
    requestId: string,
    expectedDigest: string,
    decision: "ALLOW" | "DENY",
    reason: string,
    token?: string
  ) =>
    request<AuthorizationResponse>(
      `/v1/approvals/${requestId}`,
      {
        method: "POST",
        body: JSON.stringify({
          expected_digest: expectedDigest,
          decision,
          reason,
        }),
      },
      token
    ),

  getLedgerEvents: (token?: string, limit: number = 50) =>
    request<LedgerEventItem[]>(`/v1/ledger?limit=${limit}`, { method: "GET" }, token),

  verifyLedger: (token?: string) =>
    request<LedgerVerificationResponse>("/v1/ledger/verify", { method: "GET" }, token),

  tamperLedger: (token?: string) =>
    request<{ status: string; message: string }>("/v1/ledger/tamper", { method: "POST" }, token),

  restoreLedger: (token?: string) =>
    request<{ status: string; message: string }>("/v1/ledger/restore", { method: "POST" }, token),

  getMandate: (mandateId = "mandate_default_sandbox", token?: string) =>
    request<MandateResponse>(`/v1/mandates/${mandateId}`, { method: "GET" }, token),
};
