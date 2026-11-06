import React from "react";
import { Loader2 } from "lucide-react";

export interface PillButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: React.ReactNode;
}

export const PillButton: React.FC<PillButtonProps> = ({
  children,
  variant = "primary",
  size = "md",
  loading = false,
  disabled = false,
  icon,
  className = "",
  ...props
}) => {
  const baseClasses = "pill-button";
  const variantClass = `pill-button-${variant}`;
  const sizeClass = `pill-button-${size}`;
  const loadingClass = loading ? "is-loading" : "";

  return (
    <button
      className={`${baseClasses} ${variantClass} ${sizeClass} ${loadingClass} ${className}`.trim()}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <Loader2 className="btn-spinner" size={size === "sm" ? 14 : 18} aria-hidden="true" />
      ) : (
        icon && <span className="btn-icon">{icon}</span>
      )}
      <span className="btn-text">{children}</span>
    </button>
  );
};

