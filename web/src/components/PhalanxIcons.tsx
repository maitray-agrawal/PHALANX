import React from "react";

interface SubmarkProps {
  size?: number;
  className?: string;
}

/**
 * AUTHORIZE Submark — Policy & Mandate (Rules, Limits, Control)
 * Palette: Indigo + Copper
 */
export const AuthorizeSubmark: React.FC<SubmarkProps> = ({ size = 24, className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
    {/* Shield outer boundary */}
    <path d="M32 8 L14 16 L18 42 L32 56 L46 42 L50 16 Z" stroke="#1E3A8A" strokeWidth="2.5" fill="none" />
    {/* Internal checkmark / rule chevron */}
    <path d="M22 30 L29 38 L43 24" stroke="#B87333" strokeWidth="3" strokeLinecap="square" />
    {/* Top & lateral diamond nodes */}
    <polygon points="32,4 35,8 32,12 29,8" fill="#B87333" />
    <polygon points="10,28 13,31 10,34 7,31" fill="#B87333" />
    <polygon points="54,28 57,31 54,34 51,31" fill="#B87333" />
  </svg>
);

/**
 * MONITOR Submark — Real-Time Oversight (Audit, Alerts, Anomalies)
 * Palette: Teal + Copper
 */
export const MonitorSubmark: React.FC<SubmarkProps> = ({ size = 24, className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
    {/* Geometric eye enclosure */}
    <path d="M8 32 C18 18, 46 18, 56 32 C46 46, 18 46, 8 32 Z" stroke="#0EA5A3" strokeWidth="2.5" fill="none" />
    {/* Center pupil circle & diamond core */}
    <circle cx="32" cy="32" r="8" fill="#0EA5A3" />
    <polygon points="32,27 36,32 32,37 28,32" fill="#B87333" />
    {/* Axis marks */}
    <polygon points="32,8 35,12 32,16 29,12" fill="#B87333" />
    <polygon points="32,48 35,52 32,56 29,52" fill="#B87333" />
  </svg>
);

/**
 * PROTECT Submark — Risk & Compliance (Safety, Guardrails, Trust)
 * Palette: Indigo + Teal
 */
export const ProtectSubmark: React.FC<SubmarkProps> = ({ size = 24, className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
    {/* Protective seal hexagon / shield */}
    <polygon points="32,8 52,18 52,44 32,56 12,44 12,18" stroke="#1E3A8A" strokeWidth="2" fill="none" />
    {/* Padlock center */}
    <rect x="23" y="29" width="18" height="15" fill="#1E3A8A" rx="1" />
    <path d="M26 29 V22 C26 18.7 28.7 16 32 16 C35.3 16 38 18.7 38 22 V29" stroke="#0EA5A3" strokeWidth="2.5" fill="none" />
    <circle cx="32" cy="36" r="2" fill="#FDF7EC" />
    {/* Accent node */}
    <polygon points="32,2 35,5 32,8 29,5" fill="#B87333" />
  </svg>
);

/**
 * PAYMENTS Submark — Secure Execution (Sandbox, Payouts, Orders)
 * Palette: Copper + Indigo
 */
export const PaymentsSubmark: React.FC<SubmarkProps> = ({ size = 24, className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
    {/* Credit/Payment card geometry */}
    <rect x="12" y="16" width="40" height="30" stroke="#B87333" strokeWidth="2" fill="none" />
    <line x1="12" y1="24" x2="52" y2="24" stroke="#B87333" strokeWidth="2" />
    {/* Currency / Rupee / Dollar node */}
    <circle cx="28" cy="34" r="5" stroke="#1E3A8A" strokeWidth="1.5" />
    <path d="M26 32 H30 M26 34 H29 M27 34 L29 37" stroke="#1E3A8A" strokeWidth="1.2" />
    {/* Corner verification diamond */}
    <polygon points="44,31 47,34 44,37 41,34" fill="#B87333" />
  </svg>
);

/**
 * AGENTS Submark — Autonomous Finance (MCP, Workflows, Real-World Tasks)
 * Palette: Teal + Saffron
 */
export const AgentsSubmark: React.FC<SubmarkProps> = ({ size = 24, className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
    {/* Core agent node */}
    <circle cx="32" cy="32" r="12" stroke="#0EA5A3" strokeWidth="2" fill="none" />
    <circle cx="32" cy="27" r="4" fill="#0EA5A3" />
    <path d="M24 39 C24 35, 40 35, 40 39" stroke="#0EA5A3" strokeWidth="2" strokeLinecap="round" />
    {/* Orbital control nodes */}
    <line x1="32" y1="8" x2="32" y2="20" stroke="#F59E38" strokeWidth="1.5" />
    <polygon points="32,6 35,9 32,12 29,9" fill="#F59E38" />
    <polygon points="12,32 15,35 12,38 9,35" fill="#F59E38" />
    <polygon points="52,32 55,35 52,38 49,35" fill="#F59E38" />
  </svg>
);

/**
 * AUDIT Submark — Traceability (Logs, Evidence, Governance)
 * Palette: Indigo + Copper
 */
export const AuditSubmark: React.FC<SubmarkProps> = ({ size = 24, className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
    {/* Document sheet */}
    <path d="M16 10 H38 L48 20 V52 H16 Z" stroke="#1E3A8A" strokeWidth="2" fill="none" />
    <line x1="22" y1="24" x2="34" y2="24" stroke="#1E3A8A" strokeWidth="1.5" />
    <line x1="22" y1="32" x2="40" y2="32" stroke="#1E3A8A" strokeWidth="1.5" />
    <line x1="22" y1="40" x2="32" y2="40" stroke="#1E3A8A" strokeWidth="1.5" />
    {/* Magnifier / Inspection node */}
    <circle cx="42" cy="42" r="7" stroke="#B87333" strokeWidth="2" fill="var(--ax-bg-card, #1D1814)" />
    <line x1="47" y1="47" x2="55" y2="55" stroke="#B87333" strokeWidth="2.5" />
  </svg>
);

/**
 * OUTCOMES Submark — Value & Impact (Efficiency, Scale, Safety)
 * Palette: Forest Green + Copper
 */
export const OutcomesSubmark: React.FC<SubmarkProps> = ({ size = 24, className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className}>
    {/* Trend bars */}
    <rect x="14" y="38" width="6" height="14" fill="#166534" />
    <rect x="25" y="28" width="6" height="24" fill="#166534" />
    <rect x="36" y="18" width="6" height="34" fill="#166534" />
    {/* Upward vector arrow */}
    <path d="M16 32 L34 16 L48 8" stroke="#B87333" strokeWidth="2" fill="none" />
    <polygon points="48,4 52,10 44,10" fill="#B87333" />
  </svg>
);
