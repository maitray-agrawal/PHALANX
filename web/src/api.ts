/**
 * PHALANX Real Backend API Client.
 *
 * Invariants (manual 56.41):
 * - The UI talks to the real backend only; no mocked responses in production code.
 * - All authenticated requests attach Bearer tokens and X-Phalanx-Role.
 * - Handles RFC 7807 Problem+JSON error envelopes.
 */

export interface DemoTokenResponse {
  access_token: string;
  token_type: string;
  role: string;
  expires_in_seconds: number;
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
  token?: string,
  role?: string
): Promise<T> {
  const headers = new Headers(options.headers || {});
  headers.set("Content-Type", "application/json");

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (role) {
    headers.set("X-Phalanx-Role", role);
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
  getDemoToken: (role: string, principalId = "demo-principal", agentId?: string) =>
    request<DemoTokenResponse>("/v1/auth/demo-token", {
      method: "POST",
      body: JSON.stringify({ role, principal_id: principalId, agent_id: agentId }),
    }),

  assistantChat: (message: string, agentId = "agent-auto-1", token?: string, role = "agent") =>
    request<AssistantChatResponse>(
      "/v1/assistant/chat",
      {
        method: "POST",
        body: JSON.stringify({ message, agent_id: agentId, session_id: "demo-session" }),
      },
      token,
      role
    ),

  createPaymentRequest: (cmd: AuthorizeTransactionCommand, token?: string, role = "agent") =>
    request<AuthorizationResponse>(
      "/v1/payment-requests",
      {
        method: "POST",
        body: JSON.stringify(cmd),
      },
      token,
      role
    ),

  getPendingApprovals: (token?: string, role = "approver") =>
    request<PendingStepUpItem[]>("/v1/approvals", { method: "GET" }, token, role),

  submitApproval: (
    requestId: string,
    expectedDigest: string,
    decision: "ALLOW" | "DENY",
    reason: string,
    token?: string,
    role = "approver"
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
      token,
      role
    ),

  getLedgerEvents: (token?: string, role = "auditor") =>
    request<LedgerEventItem[]>("/v1/ledger", { method: "GET" }, token, role),

  verifyLedger: (token?: string, role = "auditor") =>
    request<LedgerVerificationResponse>("/v1/ledger/verify", { method: "GET" }, token, role),

  tamperLedger: (token?: string, role = "auditor") =>
    request<{ status: string; message: string }>(
      "/v1/ledger/tamper",
      { method: "POST" },
      token,
      role
    ),

  restoreLedger: (token?: string, role = "auditor") =>
    request<{ status: string; message: string }>(
      "/v1/ledger/restore",
      { method: "POST" },
      token,
      role
    ),

  getMandate: (mandateId = "mandate_default_astra", token?: string, role = "principal") =>
    request<MandateResponse>(`/v1/mandates/${mandateId}`, { method: "GET" }, token, role),
};
