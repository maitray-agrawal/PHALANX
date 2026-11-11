# PHALANX UI Gallery

Screenshots of the PHALANX user interface captured using Playwright against a live local instance running on PostgreSQL with PayPal Sandbox credentials.

## Capture Command

To reproduce or regenerate the screenshots:

```bash
# Ensure local backend is running with PayPal sandbox credentials and demo mode:
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# Execute the capture script:
node scripts/capture_gallery.mjs
```

Environment variables accepted:
- `BASE_URL`: target server URL (default: `http://127.0.0.1:8000`)
- `ADMIN_TOKEN`: admin bearer token used for demo reset (default: `phx_admin_nxZgx2ok5QX0T_i5bW6i9A`)

---

## Desktop Screens (1920x1080)

| Screenshot | Description |
| :--- | :--- |
| `01-overview-desktop-local.png` | System overview dashboard displaying live spend vs budget, active mandates, pending approvals, and system health status. |
| `02-invoice-agent-sample-a-desktop-local.png` | Autonomous Invoice Agent processing Sample A (standard benign invoice): policy auto-approves (ALLOW) within bounds, reservation created, PayPal sandbox order generated. |
| `03-invoice-agent-sample-b-desktop-local.png` | Autonomous Invoice Agent processing Sample B (amount exceeds auto-approval threshold): policy escalates to human approval (STEP_UP) with reason codes recorded. |
| `04-invoice-agent-sample-c-desktop-local.png` | Autonomous Invoice Agent processing Sample C (adversarial prompt injection attempt in memo): extraction sanitized, malicious instructions neutralized, payment denied (DENY). |
| `05-invoice-agent-sample-d-desktop-local.png` | Autonomous Invoice Agent processing Sample D (vendor account mismatch / impersonation attempt): policy refuses automatic payment due to mandate account mismatch. |
| `06-approvals-queue-desktop-local.png` | Human-in-the-loop approvals console displaying pending step-up escalations, request provenance, and decision controls. |
| `07-approvals-refusal-desktop-local.png` | Human approvals console highlighting tamper refusal and reason codes when attempting to alter payee or amount parameters. |
| `08-attack-lab-desktop-local.png` | Attack Lab testing environment executing prompt injections, budget drain bursts, replay attacks, and mandate tampering against policy defenses. |
| `09-activity-ledger-desktop-local.png` | Tamper-evident hash-chained audit ledger showing chronological transaction events, previous event hashes, and cryptographic receipt verification. |
| `10-mandates-desktop-local.png` | Agent mandate management interface showing per-agent spending limits, allowed merchant categories, single-transaction caps, and cryptographic signature status. |
| `11-paypal-sandbox-awaiting-desktop-local.png` | Direct payment console showing PayPal Sandbox order creation and link awaiting payer approval before capture. |

---

## Mobile Screens (390x844)

| Screenshot | Description |
| :--- | :--- |
| `12-overview-mobile-local.png` | Responsive mobile dashboard displaying high-level system telemetry, active budget utilisation, and pending approvals. |
| `13-invoice-agent-mobile-local.png` | Responsive mobile view of the Invoice Agent extraction and policy authorization interface. |
| `14-approvals-mobile-local.png` | Responsive mobile view of the Human Approver exception workflow. |
| `15-activity-mobile-local.png` | Responsive mobile view of the hash-chained activity audit log. |

---

## Devpost Submission Crops (1500x1000)

Crops formatted specifically for Devpost gallery carousel requirements (1500x1000 aspect ratio) are stored in `docs/gallery/devpost/` with matching filenames.

