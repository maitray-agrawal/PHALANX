import React from "react";
import { CheckCircle2, AlertTriangle, XCircle, Shield } from "lucide-react";

export type DecisionType = "ALLOW" | "STEP_UP" | "DENY" | "FORBIDDEN" | string;

export interface DecisionBadgeProps {
  decision: DecisionType;
  showIcon?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
  label?: string;
}

export const DecisionBadge: React.FC<DecisionBadgeProps> = ({
  decision,
  showIcon = true,
  size = "md",
  className = "",
  label,
}) => {
  const normalized = decision.toUpperCase();

  let variant = "deny";
  let IconComponent = XCircle;
  let defaultLabel = "DENY";

  if (normalized === "ALLOW") {
    variant = "allow";
    IconComponent = CheckCircle2;
    defaultLabel = "ALLOW";
  } else if (normalized === "STEP_UP") {
    variant = "stepup";
    IconComponent = AlertTriangle;
    defaultLabel = "STEP_UP";
  } else if (normalized === "PRE_AUTHORIZED") {
    variant = "allow";
    IconComponent = Shield;
    defaultLabel = "PRE-AUTHORIZED";
  }

  const displayLabel = label || defaultLabel;

  return (
    <span
      className={`decision-badge badge-${variant} badge-${size} ${className}`.trim()}
      data-decision={normalized}
      data-testid="decision-badge"
    >
      {showIcon && (
        <IconComponent
          className="decision-badge-icon"
          size={size === "sm" ? 12 : size === "lg" ? 18 : 14}
          aria-hidden="true"
        />
      )}
      <span className="decision-badge-label">{displayLabel}</span>
    </span>
  );
};

