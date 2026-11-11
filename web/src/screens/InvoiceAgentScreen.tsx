import React, { useState, useEffect } from "react";
import {
  Play,
  ShieldCheck,
  ShieldAlert,
  CheckCircle2,
  Clock,
  Database,
  Cpu,
  RefreshCw,
} from "lucide-react";
import { api, type InvoiceSampleDTO, type InvoiceProcessingResultDTO } from "../api";
import { PillButton } from "../components/PillButton";
import { Skeleton } from "../components/Skeleton";

export interface InvoiceAgentScreenProps {
  token?: string;
  onNotify?: (msg: string, type: "success" | "error" | "info") => void;
}

export const InvoiceAgentScreen: React.FC<InvoiceAgentScreenProps> = ({
  token,
  onNotify,
}) => {
  const [samples, setSamples] = useState<InvoiceSampleDTO[]>([]);
  const [selectedSampleId, setSelectedSampleId] = useState<string>("sample_a");
  const [invoiceText, setInvoiceText] = useState<string>("");
  const [loadingSamples, setLoadingSamples] = useState<boolean>(true);
  const [processing, setProcessing] = useState<boolean>(false);
  const [result, setResult] = useState<InvoiceProcessingResultDTO | null>(null);

  // Load sample invoices on mount
  useEffect(() => {
    const fetchSamples = async () => {
      try {
        setLoadingSamples(true);
        const data = await api.getInvoiceSamples(token);
        setSamples(data);
        if (data.length > 0) {
          const defaultSample = data[0];
          setSelectedSampleId(defaultSample.id);
          setInvoiceText(defaultSample.text);
        }
      } catch (err: unknown) {
        const errorMsg = err instanceof Error ? err.message : "Failed to load invoice samples";
        onNotify?.(errorMsg, "error");
      } finally {
        setLoadingSamples(false);
      }
    };
    fetchSamples();
  }, [token, onNotify]);

  const handleSelectSample = (sample: InvoiceSampleDTO) => {
    setSelectedSampleId(sample.id);
    setInvoiceText(sample.text);
    setResult(null);
  };

  const handleProcessInvoice = async () => {
    if (!invoiceText.trim()) {
      onNotify?.("Invoice text cannot be empty", "error");
      return;
    }
    try {
      setProcessing(true);
      const res = await api.processInvoice(
        { invoice_text: invoiceText },
        token
      );
      setResult(res);
      onNotify?.(`Invoice processed: ${res.decision}`, res.decision === "DENY" ? "error" : "success");
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Failed to process invoice";
      onNotify?.(errorMsg, "error");
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="invoice-agent-screen-container space-y-6">
      {/* Header */}
      <div className="screen-header">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400">
            <Cpu size={24} aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-xl font-semibold tracking-tight">Invoice Agent (Autonomous AI)</h2>
            <p className="text-sm text-neutral-500">
              Gemini LLM parses untrusted supplier invoices. Deterministic PHALANX policy governs the payout.
            </p>
          </div>
        </div>
      </div>

      {/* Preset Invoices Selector */}
      <div className="card p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300">
            Select Built-in Test Invoices
          </h3>
          {loadingSamples && <Skeleton className="h-4 w-24" />}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          {samples.map((s) => {
            const isSelected = s.id === selectedSampleId;
            return (
              <button
                key={s.id}
                type="button"
                className={`p-3 text-left rounded-lg border transition-all ${
                  isSelected
                    ? "border-blue-500 bg-blue-50/50 dark:bg-blue-950/20 shadow-sm"
                    : "border-neutral-200 dark:border-neutral-800 hover:border-neutral-300"
                }`}
                onClick={() => handleSelectSample(s)}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-xs uppercase tracking-wider text-blue-600 dark:text-blue-400">
                    {s.title}
                  </span>
                  {s.id === "sample_d" && (
                    <span className="text-[10px] bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300 px-1.5 py-0.5 rounded">
                      Impersonation
                    </span>
                  )}
                  {s.id === "sample_c" && (
                    <span className="text-[10px] bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 px-1.5 py-0.5 rounded">
                      Injection
                    </span>
                  )}
                  {s.id === "sample_b" && (
                    <span className="text-[10px] bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 px-1.5 py-0.5 rounded">
                      Step-Up
                    </span>
                  )}
                  {s.id === "sample_a" && (
                    <span className="text-[10px] bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300 px-1.5 py-0.5 rounded">
                      Instant
                    </span>
                  )}
                </div>
                <p className="text-xs text-neutral-500 line-clamp-2">{s.description}</p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Invoice Raw Input & Action */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Col: Untrusted Input Text */}
        <div className="card p-4 space-y-3 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <label htmlFor="raw-invoice-text" className="text-xs font-semibold uppercase tracking-wider text-neutral-500">
                Supplier Invoice Text (Untrusted Input)
              </label>
              <span className="text-xs text-neutral-400">{invoiceText.length} / 4096 chars</span>
            </div>
            <textarea
              id="raw-invoice-text"
              rows={12}
              className="w-full font-mono text-xs p-3 rounded border border-neutral-300 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900 focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
              value={invoiceText}
              onChange={(e) => setInvoiceText(e.target.value)}
              placeholder="Paste raw invoice text here..."
            />
          </div>

          <div className="pt-2 flex items-center justify-between">
            <span className="text-xs text-neutral-500">
              Sent safely delimited as <code className="text-xs">&lt;&lt;&lt;UNTRUSTED_INVOICE_TEXT&gt;&gt;&gt;</code>
            </span>
            <PillButton
              variant="primary"
              size="md"
              icon={processing ? <RefreshCw className="animate-spin" size={16} /> : <Play size={16} />}
              onClick={handleProcessInvoice}
              disabled={processing || !invoiceText.trim()}
            >
              {processing ? "Extracting & Authorizing..." : "Run Autonomous Extraction"}
            </PillButton>
          </div>
        </div>

        {/* Right Col: Live Status & PHALANX Decision */}
        <div className="card p-4 space-y-4">
          <div className="flex items-center justify-between border-b pb-3 dark:border-neutral-800">
            <h3 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 flex items-center gap-2">
              <ShieldCheck size={18} className="text-blue-600" />
              Authorization & Guardrail Inspection
            </h3>
            {result && (
              <span
                className={`text-xs px-2 py-0.5 rounded font-mono font-medium ${
                  result.is_live
                    ? "bg-green-100 text-green-800 dark:bg-green-950/40 dark:text-green-300"
                    : "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300"
                }`}
              >
                {result.status_label}
              </span>
            )}
          </div>

          {!result && !processing && (
            <div className="py-12 text-center text-neutral-400 text-sm">
              Select an invoice above and click &quot;Run Autonomous Extraction&quot; to inspect the agent lifecycle.
            </div>
          )}

          {processing && (
            <div className="py-12 flex flex-col items-center justify-center space-y-3">
              <RefreshCw className="animate-spin text-blue-600" size={32} />
              <p className="text-xs text-neutral-500">Gemini extracting payload &amp; PHALANX evaluating policy...</p>
            </div>
          )}

          {result && (
            <div className="space-y-4 text-xs">
              {/* Decision Banner */}
              <div
                className={`p-3 rounded-lg border flex items-center justify-between ${
                  result.decision === "ALLOW"
                    ? "border-green-200 bg-green-50 text-green-900 dark:bg-green-950/30 dark:text-green-200 dark:border-green-800"
                    : result.decision === "STEP_UP"
                    ? "border-amber-200 bg-amber-50 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200 dark:border-amber-800"
                    : "border-red-200 bg-red-50 text-red-900 dark:bg-red-950/30 dark:text-red-200 dark:border-red-800"
                }`}
              >
                <div className="flex items-center space-x-2">
                  {result.decision === "ALLOW" && <CheckCircle2 size={18} className="text-green-600" />}
                  {result.decision === "STEP_UP" && <Clock size={18} className="text-amber-600" />}
                  {result.decision === "DENY" && <ShieldAlert size={18} className="text-red-600" />}
                  <div>
                    <span className="font-bold text-sm">{result.decision}</span>
                    <span className="ml-2 font-mono text-xs">({result.request_state})</span>
                  </div>
                </div>
                <span className="font-mono text-xs">{result.reasons?.join(", ") || "No reason"}</span>
              </div>

              {/* Payment Rail & Execution State */}
              <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-blue-50/70 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-900 text-blue-950 dark:text-blue-200">
                <div className="flex items-center space-x-2">
                  <span className="font-semibold text-[11px] uppercase tracking-wider text-blue-700 dark:text-blue-300">
                    Execution Rail:
                  </span>
                  <span className="font-mono text-[11px]">{result.payment_rail || "Configured Payment Rail"}</span>
                </div>
                {result.payout_id && (
                  <span className="font-mono text-[10px] bg-blue-100 dark:bg-blue-900/60 px-2 py-0.5 rounded text-blue-800 dark:text-blue-200">
                    Order Ref: {result.payout_id}
                  </span>
                )}
                {result.request_state === "AWAITING_BUYER_APPROVAL" && (
                  <span className="text-[10px] text-amber-700 dark:text-amber-300 font-medium">
                    Order Created (Awaiting Buyer Approval)
                  </span>
                )}
              </div>

              {/* Extraction Block */}
              <div>
                <span className="text-[11px] font-semibold uppercase text-neutral-500 block mb-1">
                  1. What the Agent Extracted (LLM Output)
                </span>
                <div className="bg-neutral-50 dark:bg-neutral-900 p-2.5 rounded font-mono border border-neutral-200 dark:border-neutral-800 space-y-1">
                  <div><span className="text-neutral-400">Payee:</span> {result.extraction.payee_name}</div>
                  <div>
                    <span className="text-neutral-400">Account:</span>{" "}
                    <span className={result.extraction.account.includes("attacker") ? "text-red-600 font-bold" : ""}>
                      {result.extraction.account}
                    </span>
                  </div>
                  <div>
                    <span className="text-neutral-400">Amount:</span> ${(result.extraction.amount_minor / 100).toFixed(2)} {result.extraction.currency}
                  </div>
                  {result.extraction.due_date && (
                    <div><span className="text-neutral-400">Due Date:</span> {result.extraction.due_date}</div>
                  )}
                  {result.extraction.confidence != null && (
                    <div><span className="text-neutral-400">Confidence:</span> {result.extraction.confidence}</div>
                  )}
                </div>
              </div>

              {/* Request Payload Sent to PHALANX */}
              <div>
                <span className="text-[11px] font-semibold uppercase text-neutral-500 block mb-1">
                  2. Exact Authorization Request (/v1/authorize)
                </span>
                <div className="bg-neutral-50 dark:bg-neutral-900 p-2.5 rounded font-mono border border-neutral-200 dark:border-neutral-800 max-h-24 overflow-y-auto">
                  <pre className="text-[11px] leading-tight text-neutral-700 dark:text-neutral-300">
                    {JSON.stringify(result.authorization_request, null, 2)}
                  </pre>
                </div>
              </div>

              {/* Hash-Chained Ledger Event */}
              <div>
                <span className="text-[11px] font-semibold uppercase text-neutral-500 block mb-1 flex items-center gap-1">
                  <Database size={12} /> 3. Immutable Ledger Event Record
                </span>
                <div className="bg-neutral-50 dark:bg-neutral-900 p-2.5 rounded font-mono border border-neutral-200 dark:border-neutral-800 max-h-28 overflow-y-auto">
                  <div className="text-[11px] space-y-1">
                    <div><span className="text-neutral-400">Event Type:</span> {result.ledger_event?.event_type ?? "N/A"}</div>
                    <div><span className="text-neutral-400">Request ID:</span> {result.ledger_event?.request_id ?? "N/A"}</div>
                    <div><span className="text-neutral-400">Payload Hash:</span> <span className="break-all">{result.ledger_event?.payload_hash ?? "N/A"}</span></div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
