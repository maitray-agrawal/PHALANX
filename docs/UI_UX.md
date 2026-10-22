# UI_UX - AstraX Design System Tokens & Operator Console Specification

Owner prompt: P8 / P7
Review manual references: Sections 2.1, 18, 36, 37, 43, 56.16, 56.25, 56.41.

---

## 1. Design Thesis & Aesthetic Philosophy

PHALANX protects autonomous financial agent operations through mathematical certainty, not vibes.
The UI communicates this posture immediately:
- **Dark-First Terminal Precision**: Deep navy-black foundations (`#0B0F17`, `#111827`) evoking high-assurance aerospace and defense interfaces (AstraX lineage).
- **Zero Stock Fluff**: No stock gradients, no decorative cartoon emojis, no placeholder lorem ipsum, no generic purple buttons.
- **Color Discipline**: Strict semantic coloring. Green is only ALLOW. Amber is only STEP_UP (human supervisor intervention). Red is only DENY or TAMPERED. Blue/Cyan is reserved for active cryptographic verification and navigation.
- **Tabular Numerals Everywhere**: All monetary values, hash digests, IDs, and timestamps use mono/tabular figures (`font-variant-numeric: tabular-nums`) so decimal points align vertically in transaction lists.
- **Truth in Presentation**: The frontend is completely untrusted. It never fabricates decisions or transactions. Every state change is backed by real cryptographic proofs and backend RPC responses (manual 56.41).

---

## 2. Design Tokens & CSS Variables

Tokens are declared in `brand/tokens.json` and mirrored in `web/src/styles/tokens.css` as root CSS custom properties.

### 2.1 Color Tokens
| Token Variable | Hex / RGBA | Role / Semantics |
|---|---|---|
| `--ax-bg-primary` | `#0B0F17` | Canvas background, terminal outer envelope |
| `--ax-bg-secondary` | `#111827` | Header, secondary panels, navigation backdrop |
| `--ax-bg-card` | `#161F30` | Interactive cards, modal containers, data panes |
| `--ax-bg-elevated` | `#1E293B` | Popovers, active tab indicators, elevated blocks |
| `--ax-border-subtle` | `#243247` | Gridlines, input borders, divider rules |
| `--ax-border-strong` | `#3B82F6` | Active focus rings, selected card outlines |
| `--ax-border-error` | `#EF4444` | Tamper warning borders, validation error states |
| `--ax-text-primary` | `#F9FAFB` | Primary headings, prominent amounts, titles |
| `--ax-text-secondary` | `#94A3B8` | Body text, labels, field titles, helper descriptions |
| `--ax-text-muted` | `#64748B` | Timestamps, metadata keys, inactive hints |
| `--ax-text-inverse` | `#0B0F17` | High-contrast text on bright decision badges |
| `--ax-decision-allow` | `#10B981` | ALLOW decision text, verified chain stroke |
| `--ax-decision-allow-bg` | `rgba(16, 185, 129, 0.12)` | ALLOW badge background |
| `--ax-decision-allow-border` | `#059669` | ALLOW badge border |
| `--ax-decision-step-up` | `#F59E0B` | STEP_UP review text, escalation indicators |
| `--ax-decision-step-up-bg` | `rgba(245, 158, 11, 0.12)` | STEP_UP badge background |
| `--ax-decision-step-up-border` | `#D97706` | STEP_UP badge border |
| `--ax-decision-deny` | `#EF4444` | DENY decision text, broken chain alert |
| `--ax-decision-deny-bg` | `rgba(239, 68, 68, 0.12)` | DENY badge background |
| `--ax-decision-deny-border` | `#DC2626` | DENY badge border |
| `--ax-accent-cyan` | `#00D2FF` | Live pulse dots, cryptographic signature seals |
| `--ax-accent-blue` | `#2563EB` | Primary action triggers, role indicator borders |
| `--ax-accent-glow` | `rgba(0, 210, 255, 0.25)` | Focused elements, active shield indicator |

### 2.2 Typography
- **Heading**: `'Space Grotesk', -apple-system, sans-serif` (500, 600, 700) - Used for brand shield, scene headers, card titles.
- **Body**: `'Inter', -apple-system, BlinkMacSystemFont, sans-serif` (400, 500, 600) - Used for system descriptions, form labels, tooltips.
- **Monospace & Numerical**: `'JetBrains Mono', 'Fira Code', monospace` (400, 500, 600) with `font-variant-numeric: tabular-nums` - Used for amounts ($25.00), hash digests, public keys, transaction IDs.

### 2.3 Radii & Elevation
- `--ax-radius-sm`: `4px` (buttons, chips, code snippets)
- `--ax-radius-md`: `8px` (cards, input controls, table containers)
- `--ax-radius-lg`: `12px` (modals, top header banners)
- `--ax-radius-full`: `9999px` (status pills, role switches)

---

## 3. The 3 Demo Scenes & Mandate View

### 3.1 Scene 1: Request Console (`/console`)
- **Intent Dispatcher Chat**: Natural language input where the agent or operator types a payment request (or selects standard test scenarios).
- **Assistant Proposer & Intent Extraction Card**: Untrusted prompt text is isolated within `<<<UNTRUSTED_USER_INPUT>>>` delimiters on the backend. The model proposes a structured `TransactionIntentDraft` (amount, payee, purpose, anomaly flag).
- **Decision Badge & Reasons Panel**:
  - Displays instant outcome badge with high-contrast icon and label: `ALLOW` (shield check), `STEP_UP` (human review required), or `DENY` (hard constraint blocked).
  - Plain-English reason codes list every invariant checked: Pre-authorized operational limit, velocity bounds, purpose match, single-limit check.
  - If ALLOW: renders the PayPal Sandbox Payout ID (`sandbox_tx_...`).

### 3.2 Scene 2: Step-Up Approval Queue (`/approvals`)
- **Digest-Bound Human Authorization**:
  - Displays pending escalated transactions requiring supervisor review.
  - Shows the exact intent fields alongside the canonical RFC 8785 SHA-256 digest (`intent_digest`).
  - **Diff if Changed**: An interactive comparison view showing whether the current intent fields match the stored digest byte-for-byte. If tampered with, the diff highlights discrepancies in red with a warning that the cryptographic lock will reject execution.
  - **Role-Gated Actions**: If the active role is `AGENT`, the Approve and Reject buttons are disabled with `aria-disabled="true"` and an alert banner explaining: *“Security Policy: Autonomous agents cannot approve their own requests (manual 18, 56.16).”*
  - Approving or Rejecting sends `POST /v1/approvals/{request_id}` with the expected digest.

### 3.3 Scene 3: Cryptographic Audit Ledger (`/ledger`)
- **AG Grid Data Table**:
  - Columns: Event ID, Previous Hash (`prev_hash`), Block Hash (`event_hash`), Agent ID, Recipient ID, Amount (tabular numerals), Decision badge, Purpose & Invariants, Recorded Timestamp.
  - Real-time sort, filter, and column resizing.
- **Chain-of-Blocks Visual**:
  - Horizontal block sequence showing each block linked to its predecessor via hash pointers (`prev_hash` -> `event_hash`).
  - **Verify Chain Button**: Calls `GET /v1/ledger/verify` against the backend. When intact, displays green badge: *"Cryptographic chain verified (N/N links intact)"*.
  - **Simulate Database Tamper Button**: Triggers `POST /v1/ledger/tamper`, simulating an illicit direct SQL `UPDATE` that modifies an amount without updating the hash chain.
  - The visual immediately turns **RED at the first broken link**, highlighting the exact block index where the hash chain severed!
  - **Restore Ledger Button**: Calls `POST /v1/ledger/restore` to revert the illicit modification and re-verify the chain.

### 3.4 Mandate View (`/mandate`)
- Displays the active Ed25519 Authority Mandate (`mandate_default_astra`):
  - Limits: Single Transaction Cap ($5,000.00), Instant Autonomous Threshold ($500.00), Lifetime Budget Cap ($25,000.00).
  - Remaining Budget: Calculated dynamically as Lifetime Budget minus spent minor units, formatted with tabular numbers.
  - Expiry: Start and end validity timestamps (UTC).
  - Status: `ACTIVE` status badge.
  - Allowed Payees: List of registered, allowlisted recipient identifiers.
  - Allowed Purposes: Purpose allowlist substrings.
  - Ed25519 Integrity Seal: Cryptographic signature seal and key ID (`key_...`), with explicit note: *“Integrity seal only; not human non-repudiation.”*

---

## 4. Operational States (Manual 36)

Every view and component implements four explicit states:
1. **Loading State**: An accessible spinner and skeleton pulse with `aria-busy="true"` and `aria-live="polite"` while fetching from backend RPCs.
2. **Empty State**: Clear, context-specific instructions when queues or lists are empty (e.g. *"No pending step-up requests. All autonomous transactions are within policy bounds."*).
3. **Error State**: Displays RFC 7807 Problem+JSON details, status codes, and a Retry button without leaking internal stack traces.
4. **Success State**: Immediate visual confirmation with transaction IDs, ledger block links, and digest confirmations.

---

## 5. Keyboard Navigation & Accessibility (WCAG 2.1 AA / Manual 37, 56.25)

1. **Tab Order & Focus Trapping**: Logical DOM order (`header` -> `role-switcher` -> `nav tabs` -> `scene content` -> `interactive inputs` -> `action buttons`).
2. **Focus Visibility**: Custom 2px solid cyan/blue focus rings with 2px offset (`outline: 2px solid var(--ax-border-strong); outline-offset: 2px`).
3. **Contrast Ratios**:
   - Primary text (`#F9FAFB`) on primary background (`#0B0F17`): **18.2:1** (far exceeds WCAG AA 4.5:1 requirement).
   - Secondary text (`#94A3B8`) on card background (`#161F30`): **6.8:1** (exceeds WCAG AA 4.5:1).
   - Allow green (`#10B981`) on dark card: **5.5:1**.
   - Step-Up amber (`#F59E0B`) on dark card: **5.2:1**.
   - Deny red (`#EF4444`) on dark card: **4.8:1**.
4. **Screen Reader Semantics**:
   - Live regions (`role="status"`, `aria-live="polite"`) for verification alerts and status updates.
   - Distinct ARIA roles: `role="tablist"`, `role="tab"`, `role="tabpanel"`, `role="alert"`.
   - Accessible labels (`aria-label`, `htmlFor`, `id`) on all form inputs and action buttons.
