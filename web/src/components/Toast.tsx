import React, { useEffect } from "react";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";

export interface ToastProps {
  id?: string;
  type?: "success" | "error" | "info";
  message: string;
  onDismiss: () => void;
  durationMs?: number;
}

export const Toast: React.FC<ToastProps> = ({
  type = "info",
  message,
  onDismiss,
  durationMs = 4000,
}) => {
  useEffect(() => {
    if (durationMs > 0) {
      const timer = setTimeout(onDismiss, durationMs);
      return () => clearTimeout(timer);
    }
  }, [durationMs, onDismiss]);

  const IconComponent =
    type === "success" ? CheckCircle2 : type === "error" ? AlertCircle : Info;

  return (
    <div
      className={`toast-container toast-${type}`}
      role="status"
      aria-live="polite"
    >
      <IconComponent className="toast-icon" size={18} aria-hidden="true" />
      <span className="toast-message">{message}</span>
      <button
        className="toast-close"
        onClick={onDismiss}
        aria-label="Dismiss notification"
      >
        <X size={14} aria-hidden="true" />
      </button>
    </div>
  );
};

